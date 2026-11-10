#!/usr/bin/env python3
"""
FRED Metadata Catalog loader.

Pulls metadata from the FRED / ALFRED API, keeps every raw payload unchanged on
disk (payloads/*.json plus a SHA-256 manifest, the Data_Retrival raw-artifact
rule), loads the parsed rows into PostgreSQL (fred_schema.sql), and writes the
compact catalog CSVs that neo4j/cypher/004_fred_catalog_load.cypher imports
with LOAD CSV from data/catalog/neo4j-import/fred_catalog/.
Observations go to PostgreSQL only; they are never exported for the graph.

    export FRED_API_KEY=...
    python fred_load.py --releases 50 10 53 13 --observations UNRATE PAYEMS GDPC1 CPIAUCSL INDPRO --max-series 100
    python fred_load.py --updates                 # what changed since the last load (series/updates)
    python fred_load.py --documents --releases 50 13 --doc-last 6     # dated PDFs + every release page -> 005 CSVs
    python fred_load.py --category-crawl data/catalog/fred/crawls/active/all_categories.csv
    python fred_load.py --observations-all            # every vintage for catalog series with none yet
    python fred_load.py --series-file data/catalog/fred/lists/datalist_369765.tsv   # a FRED data list

Dependencies: requests, psycopg (v3). Neo4j is loaded from the CSVs by running
003, 004 (and 005) in cypher-shell, so no Neo4j driver is needed here.
"""
import argparse, csv, datetime, hashlib, json, os, pathlib, time
from html.parser import HTMLParser
from urllib.parse import urlsplit
import requests
import psycopg

API = "https://api.stlouisfed.org/fred"
KEY = os.environ.get("FRED_API_KEY")
PAYLOADS = pathlib.Path(os.environ.get("FRED_PAYLOADS", "payloads")); PAYLOADS.mkdir(parents=True, exist_ok=True)
# Host-writable staging; the container-owned data/catalog/neo4j-import is filled by
# docker cp (run_all.sh). Override with NEO4J_IMPORT.
NEO_IMPORT = pathlib.Path(os.environ.get("NEO4J_IMPORT", "data/staging/neo4j-import")) / "fred_catalog"
NEO_IMPORT.mkdir(parents=True, exist_ok=True)
MANIFEST = {}
PG = os.environ.get("FRED_PG", "dbname=fred")

ALL_VINTAGES = {"realtime_start": "1776-07-04", "realtime_end": "9999-12-31"}
OPEN_END = "9999-12-31"
NOT_IN_ALFRED = "does not exist in ALFRED"   # FRED's 400 text for series with no vintage history
TOO_MANY_VINTAGES = "exceeds the maximum number of vintage dates"   # ALFRED: at most 2,000 per request
VINTAGE_WINDOW = 1900   # ALFRED counts the window start too; 2000 per window overflowed by one


MIN_INTERVAL = 0.55  # seconds between requests: FRED allows 120 req/min
_last_call = [0.0]


def _request(endpoint: str, params: dict) -> dict:
    """One HTTP request, throttled globally, retried on 429 / 5xx with backoff."""
    for attempt in range(6):
        wait = _last_call[0] + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()
        try:
            r = requests.get(f"{API}/{endpoint}", params=params, timeout=60)
        except requests.RequestException as exc:
            # timeouts and resets are retried like 429/5xx; requests' own message
            # embeds the URL, which carries api_key, so it is never surfaced
            last_error = f"{type(exc).__name__} (request URL withheld)"
            if attempt == 5:
                raise RuntimeError(f"FRED {endpoint}: {last_error} after {attempt + 1} attempts") from None
            time.sleep(min(60, 5 * 2 ** attempt))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(60, 5 * 2 ** attempt))
            continue
        if r.status_code != 200:
            try:
                detail = r.json().get("error_message", r.reason)
            except ValueError:
                detail = r.reason
            raise RuntimeError(f"FRED {endpoint}: HTTP {r.status_code}: {detail}")
        return r.json()
    raise RuntimeError(f"FRED {endpoint}: gave up after {attempt + 1} attempts (HTTP {r.status_code})")


def get(endpoint: str, page_size: int = 1000, **params) -> dict:
    """One FRED call, paged to completion, returned as a single merged payload.
    Most endpoints cap limit at 1000; series/observations allows 100000."""
    params |= {"api_key": KEY, "file_type": "json", "limit": page_size, "offset": 0}
    merged, key = None, None
    while True:
        page = _request(endpoint, params)
        if merged is None:
            merged = page
            key = next(k for k, v in page.items() if isinstance(v, list))
        else:
            merged[key].extend(page[key])
        if page.get("offset", 0) + page.get("limit", 0) >= page.get("count", 0):
            return merged
        params["offset"] += page_size


def get_one(endpoint: str, **params) -> dict:
    """One FRED call without paging, for endpoints whose payload is a dict
    (release/tables returns {"elements": {id: element}})."""
    return _request(endpoint, params | {"api_key": KEY, "file_type": "json"})


def crawl_release_tables(rid: int) -> list[dict]:
    """Every element of a release's table tree. release/tables is lazy at the
    top: the root call lists sections with no children, a section call lists
    its tables with no children, and a table call returns the table's whole
    nested tree. So: walk whatever is nested, and call FRED only for elements
    that came back unexpanded. Breadth-first, so parents precede children."""
    out, seen, queue = [], set(), [None]

    def take(e: dict) -> None:
        if e["element_id"] in seen:
            return
        seen.add(e["element_id"]); out.append(e)
        kids = e.get("children") or {}
        kids = list(kids.values()) if isinstance(kids, dict) else list(kids)
        if kids:
            for k in kids:
                take(k)
        elif e["type"] != "series":
            queue.append(e["element_id"])

    while queue:
        eid = queue.pop(0)
        res = get_one("release/tables", release_id=rid, **({"element_id": eid} if eid else {}))
        els = res.get("elements") or {}
        for e in (els.values() if isinstance(els, dict) else els):   # FRED sends [] when empty
            take(e)
    return out


def release_table_csv(cur) -> None:
    """release_table_elements.csv from the database, parents before children,
    so it covers every release crawled so far, not only this run's."""
    cur.execute("""
        WITH RECURSIVE t AS (
            SELECT element_id, 0 AS depth FROM release_table_element WHERE parent_id IS NULL
            UNION ALL
            SELECT c.element_id, t.depth + 1 FROM release_table_element c JOIN t ON c.parent_id = t.element_id)
        SELECT e.element_id, e.release_id, e.parent_id, e.element_type, e.element_name, e.element_level, e.line_no, e.series_id
        FROM release_table_element e JOIN t USING (element_id) ORDER BY t.depth, e.element_id""")
    write_csv("release_table_elements", RTE_COLS,
              [tuple("" if v is None else v for v in r) for r in cur.fetchall()])


def tables_and_vintages(conn, release_ids: list[int], tables: bool, vintages: bool, refresh: bool = False) -> None:
    """release/tables for the given releases (skipping ones already crawled
    unless refresh) and series/vintagedates for every catalog series."""
    with conn.cursor() as cur:
        if tables:
            for rid in release_ids:
                cur.execute("SELECT count(*) FROM release_table_element WHERE release_id = %s", (rid,))
                if cur.fetchone()[0] and not refresh:
                    print(f"release/tables {rid}: already loaded, skipped (use --refresh)", flush=True)
                    continue
                elements = crawl_release_tables(rid)
                save(f"release_tables_{rid}", {"release_id": rid, "elements": elements})
                rows = [element_row(e) for e in elements]
                upsert(cur, "release_table_element", RTE_COLS, rows, ["element_id"])
                conn.commit()
                print(f"release/tables {rid}: {len(rows)} elements, "
                      f"{sum(1 for r in rows if r[3] == 'series')} series rows", flush=True)
        if vintages:
            cur.execute("SELECT series_id FROM series ORDER BY series_id")
            ids = [r[0] for r in cur.fetchall()]
            vint = {}
            for i, sid in enumerate(ids, 1):
                vd = get("series/vintagedates", series_id=sid)
                vint[sid] = vd["vintage_dates"]
                upsert(cur, "vintage_date", ["series_id", "vintage_date"],
                       [(sid, d) for d in vd["vintage_dates"]], ["series_id", "vintage_date"])
                if i % 50 == 0:
                    conn.commit(); print(f"series/vintagedates: {i}/{len(ids)}", flush=True)
            save("vintage_dates", vint)
            conn.commit()
            print(f"series/vintagedates: {sum(len(v) for v in vint.values())} dates over {len(vint)} series", flush=True)
        release_table_csv(cur)


def element_row(e: dict) -> tuple:
    return (e["element_id"], e["release_id"], e.get("parent_id"), e["type"], (e.get("name") or "")[:300],
            int(e.get("level") or 0), e.get("line"), e.get("series_id") or None)


RTE_COLS = ["element_id", "release_id", "parent_id", "element_type", "element_name", "element_level", "line_no", "series_id"]


def save(name: str, payload) -> None:
    """Raw artifact: written once, hashed, never edited."""
    path = PAYLOADS / f"{name}.json"
    text = json.dumps(payload, indent=1)
    path.write_text(text)
    MANIFEST[path.name] = {"sha256": hashlib.sha256(text.encode()).hexdigest(), "bytes": len(text),
                           "retrieved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def write_csv(name: str, header: list[str], rows) -> None:
    """Compact catalog CSV for Neo4j LOAD CSV (column names match 004)."""
    with open(NEO_IMPORT / f"{name}.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(header); w.writerows(rows)


def upsert(cur, table: str, cols: list[str], rows: list[tuple], key: list[str]) -> None:
    if not rows:
        return
    sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in key) or None
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(cols))}) "
           f"ON CONFLICT ({', '.join(key)}) " + (f"DO UPDATE SET {sets}" if sets else "DO NOTHING"))
    cur.executemany(sql, rows)


def main(release_ids: list[int], obs_series: list[str], max_series: int | None = None,
         tables: bool = True, vintages: bool = True) -> None:
    with psycopg.connect(PG) as conn, conn.cursor() as cur:
        # --- sources and releases -------------------------------------------------
        sources = get("sources"); save("sources", sources)
        upsert(cur, "source", ["source_id", "source_name", "source_link"],
               [(s["id"], s["name"], s.get("link")) for s in sources["sources"]], ["source_id"])

        releases = get("releases"); save("releases", releases)
        upsert(cur, "release", ["release_id", "release_name", "press_release", "release_link"],
               [(r["id"], r["name"], bool(r["press_release"]), r.get("link")) for r in releases["releases"]],
               ["release_id"])

        # --- every release gets its sources and its dates (ERD rule 1: a release is
        # published by at least one source; audit A06). Sources need one call per
        # release (no bulk endpoint); dates come from the bulk releases/dates call.
        all_release_ids = [r["id"] for r in releases["releases"]]
        rs_payloads, rd_payloads, series_rows, lookups = [], [], [], {"frequency": {}, "units": {}, "sa": {}}
        today = time.strftime("%Y-%m-%d")
        for rid in all_release_ids:
            rs = get("release/sources", release_id=rid); rs["release_id"] = rid; rs_payloads.append(rs)
            upsert(cur, "release_source", ["release_id", "source_id"],
                   [(rid, s["id"]) for s in rs["sources"]], ["release_id", "source_id"])
        print(f"release/sources: {len(rs_payloads)} releases, "
              f"{sum(len(rs['sources']) for rs in rs_payloads)} links", flush=True)

        bulk = get("releases/dates", include_release_dates_with_no_data="true",
                   realtime_start="1776-07-04", realtime_end="9999-12-31")
        by_release: dict[int, list[dict]] = {}
        for d in bulk["release_dates"]:
            by_release.setdefault(d["release_id"], []).append(d)
        for rid in all_release_ids:
            dates = by_release.get(rid, [])
            rd_payloads.append({"release_id": rid, "release_dates": dates})
            upsert(cur, "release_date", ["release_id", "release_date", "date_status"],
                   [(rid, d["date"], "actual" if d["date"] <= today else "scheduled") for d in dates],
                   ["release_id", "release_date"])
        print(f"releases/dates: {len(bulk['release_dates'])} dates over {len(by_release)} releases", flush=True)
        conn.commit()   # the release phase stands on its own; a failure below keeps it

        for rid in release_ids:
            ser = get("release/series", release_id=rid); ser["release_id"] = rid; save(f"series_{rid}", ser)
            keep = ser["seriess"]
            if max_series is not None:
                # top N by popularity, plus any requested observation series in this release
                ranked = sorted(keep, key=lambda s: -(s.get("popularity") or 0))
                keep = ranked[:max_series] + [s for s in ranked[max_series:] if s["id"] in obs_series]
            for s in keep:
                lookups["frequency"][s["frequency_short"]] = s["frequency"]
                lookups["units"][s["units_short"]] = s["units"]
                lookups["sa"][s["seasonal_adjustment_short"]] = s["seasonal_adjustment"]
                series_rows.append((s["id"], s["title"], rid, s["frequency_short"], s["units_short"],
                                    s["seasonal_adjustment_short"], s["observation_start"], s["observation_end"],
                                    s["last_updated"][:19], s.get("popularity"), s.get("notes")))
        save("release_sources", {"items": rs_payloads}); save("release_dates", {"items": rd_payloads})

        upsert(cur, "frequency", ["frequency_code", "frequency_name"], list(lookups["frequency"].items()), ["frequency_code"])
        upsert(cur, "units", ["units_code", "units_name"], list(lookups["units"].items()), ["units_code"])
        upsert(cur, "seasonal_adjustment", ["sa_code", "sa_name"], list(lookups["sa"].items()), ["sa_code"])
        upsert(cur, "series", ["series_id", "title", "release_id", "frequency_code", "units_code", "sa_code",
                               "observation_start", "observation_end", "last_updated", "popularity", "notes"],
               series_rows, ["series_id"])

        categories_and_tags(cur, [r[0] for r in series_rows])
        conn.commit()

        tables_and_vintages(conn, release_ids, tables, vintages)

        catalog_csvs(cur)
        conn.commit()
        # --- observations, every vintage (ALFRED), PostgreSQL only ----------------
        load_observations(conn, obs_series)
    (PAYLOADS / "manifest.json").write_text(json.dumps(MANIFEST, indent=1))
    print(f"loaded {len(series_rows)} series from {len(release_ids)} releases")
    print(f"raw payloads + manifest: {PAYLOADS.resolve()}")
    print(f"neo4j CSVs: {NEO_IMPORT.resolve()}  (run 003 then 004 with :param snapshot_id)")


def categories_and_tags(cur, series_ids: list[str], tag: str = "") -> None:
    """series/categories and series/tags for each series, every category walked
    up to the root so each parent_id resolves, all upserted. `tag` suffixes the
    raw payload names so a list load does not overwrite the release load's."""
    cats, tags_out, cat_rows, tag_rows = {}, [], [], {}
    for sid in series_ids:
        sc = get("series/categories", series_id=sid); sc["series_id"] = sid; cats[sid] = sc
        for c in sc["categories"]:
            cat_rows.append((c["id"], c["name"], c.get("parent_id")))
        st = get("series/tags", series_id=sid); st["series_id"] = sid; tags_out.append(st)
        for t in st["tags"]:
            tag_rows[t["name"]] = (t["name"], t["group_id"], t.get("notes"), t.get("popularity"))
    save(f"series_categories{tag}", {"items": list(cats.values())}); save(f"series_tags{tag}", {"items": tags_out})

    # walk each category up to the root so every parent_id resolves
    seen = {c[0] for c in cat_rows}
    frontier = {c[2] for c in cat_rows if c[2] is not None and c[2] not in seen}
    while frontier:
        cid = frontier.pop()
        c = get("category", category_id=cid)["categories"][0]
        cat_rows.append((c["id"], c["name"], c.get("parent_id"))); seen.add(c["id"])
        if c.get("parent_id") is not None and c["parent_id"] not in seen and c["parent_id"] != c["id"]:
            frontier.add(c["parent_id"])
    save(f"categories{tag}", {"categories": [{"id": a, "name": b, "parent_id": c} for a, b, c in cat_rows]})
    # parents before children: FRED's root (0) lists itself as its own parent, so
    # that becomes NULL; then insert level by level so every FK target exists.
    cat_rows = [(a, b, None if c == a else c) for a, b, c in {r[0]: r for r in cat_rows}.values()]
    ordered, placed, pending = [], set(), list(cat_rows)
    while pending:
        level = [r for r in pending if r[2] is None or r[2] in placed]
        if not level:
            raise RuntimeError(f"category parents missing for {[r[0] for r in pending]}")
        ordered += level; placed |= {r[0] for r in level}
        pending = [r for r in pending if r[0] not in placed]
    upsert(cur, "category", ["category_id", "category_name", "parent_id"], ordered, ["category_id"])
    upsert(cur, "series_category", ["series_id", "category_id"],
           [(sid, c["id"]) for sid, sc in cats.items() for c in sc["categories"]], ["series_id", "category_id"])

    groups = {"freq": "Frequency", "gen": "General or Concept", "geo": "Geography", "geot": "Geography Type",
              "rls": "Release", "seas": "Seasonal Adjustment", "src": "Source", "cc": "Citation & Copyright"}
    upsert(cur, "tag_group", ["group_id", "group_name"], list(groups.items()), ["group_id"])
    upsert(cur, "tag", ["tag_name", "group_id", "tag_notes", "popularity"], list(tag_rows.values()), ["tag_name"])
    upsert(cur, "series_tag", ["series_id", "tag_name"],
           [(st["series_id"], t["name"]) for st in tags_out for t in st["tags"]], ["series_id", "tag_name"])


def catalog_csvs(cur) -> None:
    """The Neo4j catalog CSVs for 004, read from PostgreSQL, so the graph gets
    every catalog series whichever load mode put it there (release walk or
    --series-file). Categories: those any series sits in, plus their ancestors."""
    q = lambda sql: [tuple("" if v is None else v for v in r) for r in (cur.execute(sql) or cur).fetchall()]
    write_csv("sources", ["source_id", "source_name", "source_link"],
              q("SELECT source_id, source_name, source_link FROM source ORDER BY source_id"))
    write_csv("releases", ["release_id", "release_name", "press_release", "release_link"],
              q("SELECT release_id, release_name, CASE WHEN press_release THEN 'true' ELSE 'false' END, release_link "
                "FROM release ORDER BY release_id"))
    write_csv("release_sources", ["release_id", "source_id"],
              q("SELECT release_id, source_id FROM release_source ORDER BY 1, 2"))
    write_csv("release_dates", ["release_id", "release_date", "date_status"],
              q("SELECT release_id, to_char(release_date, 'YYYY-MM-DD'), "
                "CASE WHEN release_date <= CURRENT_DATE THEN 'actual' ELSE 'scheduled' END "
                "FROM release_date ORDER BY 1, 2"))
    write_csv("series", ["series_id", "title", "release_id", "frequency_code", "frequency_name", "units_code",
                         "units_name", "sa_code", "sa_name", "observation_start", "observation_end",
                         "last_updated", "popularity", "notes"],
              q("SELECT s.series_id, s.title, s.release_id, s.frequency_code, f.frequency_name, s.units_code, "
                "u.units_name, s.sa_code, a.sa_name, to_char(s.observation_start, 'YYYY-MM-DD'), "
                "to_char(s.observation_end, 'YYYY-MM-DD'), to_char(s.last_updated, 'YYYY-MM-DD HH24:MI:SS'), "
                "s.popularity, s.notes FROM series s JOIN frequency f USING (frequency_code) "
                "JOIN units u USING (units_code) JOIN seasonal_adjustment a USING (sa_code) "
                "ORDER BY s.popularity DESC NULLS LAST, s.series_id"))
    write_csv("categories", ["category_id", "category_name", "parent_id"],
              q("WITH RECURSIVE up AS (SELECT DISTINCT category_id FROM series_category "
                "  UNION SELECT c.parent_id FROM category c JOIN up USING (category_id) WHERE c.parent_id IS NOT NULL), "
                "down AS (SELECT category_id, 0 AS depth FROM category WHERE parent_id IS NULL "
                "  UNION ALL SELECT c.category_id, d.depth + 1 FROM category c JOIN down d ON c.parent_id = d.category_id) "
                "SELECT c.category_id, c.category_name, c.parent_id FROM category c "
                "JOIN up USING (category_id) JOIN down USING (category_id) ORDER BY down.depth, c.category_id"))
    write_csv("series_categories", ["series_id", "category_id"],
              q("SELECT series_id, category_id FROM series_category ORDER BY 1, 2"))
    write_csv("tag_groups", ["group_id", "group_name"], q("SELECT group_id, group_name FROM tag_group ORDER BY 1"))
    write_csv("tags", ["tag_name", "group_id", "tag_notes", "popularity"],
              q("SELECT tag_name, group_id, tag_notes, popularity FROM tag t "
                "WHERE EXISTS (SELECT 1 FROM series_tag st WHERE st.tag_name = t.tag_name) ORDER BY 1"))
    write_csv("series_tags", ["series_id", "tag_name"], q("SELECT series_id, tag_name FROM series_tag ORDER BY 1, 2"))
    release_table_csv(cur)


def series_list(path: pathlib.Path, vintages: bool = True, refresh: bool = False) -> None:
    """A hand-picked list of series (one id per line, first tab-separated
    column; '#' lines and a 'series_id' header are skipped), whatever releases
    they belong to: series + series/release per id, then categories, tags,
    vintage dates and every vintage of observations for the ids with none yet.
    Ids FRED does not know are reported and skipped. Ends with the catalog CSVs.
    Resumable: without refresh, ids already in the series table skip the
    metadata calls and ids that already have vintage dates skip those."""
    ids, seen = [], set()
    for line in path.read_text().splitlines():
        sid = line.split("\t")[0].strip()
        if sid and not sid.startswith("#") and sid != "series_id" and sid not in seen:
            seen.add(sid); ids.append(sid)
    tag = "_" + path.stem
    with psycopg.connect(PG) as conn, conn.cursor() as cur:
        cur.execute("SELECT release_id FROM release"); known = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT series_id FROM series"); catalogued = {r[0] for r in cur.fetchall()}
        listed, ids = ids, (ids if refresh else [i for i in ids if i not in catalogued])
        print(f"{len(listed)} listed, {len(listed) - len(ids)} already catalogued, "
              f"{len(ids)} to fetch metadata for", flush=True)
        series_rows, lookups, raw, missing = [], {"frequency": {}, "units": {}, "sa": {}}, [], []
        for i, sid in enumerate(ids, 1):
            try:
                s = get_one("series", series_id=sid)["seriess"][0]
                r = get_one("series/release", series_id=sid)["releases"][0]
            except (RuntimeError, IndexError, KeyError) as exc:
                missing.append(sid); print(f"[{i}/{len(ids)}] {sid}: SKIPPED {exc}", flush=True)
                continue
            raw.append({"series": s, "release": r})
            if r["id"] not in known:   # a release FRED added since the catalog load
                upsert(cur, "release", ["release_id", "release_name", "press_release", "release_link"],
                       [(r["id"], r["name"], bool(r["press_release"]), r.get("link"))], ["release_id"])
                rs = get("release/sources", release_id=r["id"])
                upsert(cur, "source", ["source_id", "source_name", "source_link"],
                       [(x["id"], x["name"], x.get("link")) for x in rs["sources"]], ["source_id"])
                upsert(cur, "release_source", ["release_id", "source_id"],
                       [(r["id"], x["id"]) for x in rs["sources"]], ["release_id", "source_id"])
                known.add(r["id"])
            lookups["frequency"][s["frequency_short"]] = s["frequency"]
            lookups["units"][s["units_short"]] = s["units"]
            lookups["sa"][s["seasonal_adjustment_short"]] = s["seasonal_adjustment"]
            series_rows.append((s["id"], s["title"], r["id"], s["frequency_short"], s["units_short"],
                                s["seasonal_adjustment_short"], s["observation_start"], s["observation_end"],
                                s["last_updated"][:19], s.get("popularity"), s.get("notes")))
            if i % 100 == 0:
                print(f"series metadata: {i}/{len(ids)}", flush=True)
        save(f"series{tag}", {"source": str(path), "items": raw, "missing": missing})
        upsert(cur, "frequency", ["frequency_code", "frequency_name"], list(lookups["frequency"].items()), ["frequency_code"])
        upsert(cur, "units", ["units_code", "units_name"], list(lookups["units"].items()), ["units_code"])
        upsert(cur, "seasonal_adjustment", ["sa_code", "sa_name"], list(lookups["sa"].items()), ["sa_code"])
        upsert(cur, "series", ["series_id", "title", "release_id", "frequency_code", "units_code", "sa_code",
                               "observation_start", "observation_end", "last_updated", "popularity", "notes"],
               series_rows, ["series_id"])
        conn.commit()
        print(f"series: {len(series_rows)} upserted, {len(missing)} unknown to FRED", flush=True)
        if series_rows:
            categories_and_tags(cur, [r[0] for r in series_rows], tag); conn.commit()
        cur.execute("SELECT series_id FROM series WHERE series_id = ANY(%s)", (listed,))
        got = sorted({r[0] for r in cur.fetchall()}, key=listed.index)
        if vintages:
            cur.execute("SELECT DISTINCT series_id FROM vintage_date WHERE series_id = ANY(%s)", (got,))
            have = set() if refresh else {r[0] for r in cur.fetchall()}
            todo_v, vint, fred_only = [x for x in got if x not in have], {}, []
            print(f"series/vintagedates: {len(todo_v)} to fetch ({len(have)} already have them)", flush=True)
            for i, sid in enumerate(todo_v, 1):
                try:
                    vd = get("series/vintagedates", series_id=sid)
                except RuntimeError as exc:
                    if NOT_IN_ALFRED not in str(exc):
                        raise
                    fred_only.append(sid); continue
                vint[sid] = vd["vintage_dates"]
                upsert(cur, "vintage_date", ["series_id", "vintage_date"],
                       [(sid, d) for d in vd["vintage_dates"]], ["series_id", "vintage_date"])
                if i % 100 == 0:
                    conn.commit(); print(f"series/vintagedates: {i}/{len(todo_v)}", flush=True)
            save(f"vintage_dates{tag}", {"vintage_dates": vint, "fred_only": fred_only}); conn.commit()
            print(f"series/vintagedates: {len(vint)} series; {len(fred_only)} FRED-only (no ALFRED history): "
                  f"{' '.join(fred_only)}", flush=True)
        catalog_csvs(cur)
        cur.execute("SELECT s FROM unnest(%s::text[]) s WHERE NOT EXISTS "
                    "(SELECT 1 FROM observation o WHERE o.series_id = s)", (got,))
        todo = [r[0] for r in cur.fetchall()]
        print(f"observations: {len(todo)} of {len(got)} list series have none yet", flush=True)
        failed = load_observations(conn, todo)
    (PAYLOADS / "manifest.json").write_text(json.dumps(MANIFEST, indent=1))
    if missing or failed:
        print(f"unknown: {' '.join(missing) or '-'}\nobservations failed: {' '.join(failed) or '-'}")
    raise SystemExit(1 if failed else 0)


def fetch_observation_rows(sid: str) -> tuple[dict, list[tuple]]:
    """Every vintage of one series from ALFRED, as observation rows."""
    try:
        ob = get("series/observations", page_size=100000, series_id=sid, **ALL_VINTAGES)
        rows = [(sid, o["date"], o["realtime_start"], o["realtime_end"],
                 None if o["value"] == "." else o["value"]) for o in ob["observations"]]
    except RuntimeError as exc:
        if TOO_MANY_VINTAGES in str(exc):
            return fetch_observation_rows_windowed(sid)
        if NOT_IN_ALFRED not in str(exc):
            raise
        # FRED-only series (mostly third-party market data): no vintage history.
        # Keep today's values as the one open window, first seen today.
        ob = get("series/observations", page_size=100000, series_id=sid)
        ob["alfred"] = False
        rows = [(sid, o["date"], o["realtime_start"], OPEN_END,
                 None if o["value"] == "." else o["value"]) for o in ob["observations"]]
    # order by realtime_start so the BEFORE INSERT trigger closes vintages in sequence
    rows.sort(key=lambda r: (r[1], r[2]))
    return ob, rows


def fetch_observation_rows_windowed(sid: str) -> tuple[dict, list[tuple]]:
    """ALFRED refuses one request spanning more than 2,000 vintage dates. Split
    the real-time axis at every 2,000th vintage date, fetch each window, then
    stitch: a vintage that spans a window edge comes back clipped in both
    windows (same value, touching dates), so those pieces are joined again."""
    vds = get("series/vintagedates", series_id=sid)["vintage_dates"]
    starts = [ALL_VINTAGES["realtime_start"]] + vds[VINTAGE_WINDOW::VINTAGE_WINDOW]
    ends = [str(datetime.date.fromisoformat(d) - datetime.timedelta(days=1)) for d in starts[1:]] + [OPEN_END]
    pieces, payloads = [], []
    for a, b in zip(starts, ends):
        ob = get("series/observations", page_size=100000, series_id=sid, realtime_start=a, realtime_end=b)
        payloads.append({"realtime_start": a, "realtime_end": b, "observations": ob["observations"]})
        pieces += [(o["date"], o["realtime_start"], o["realtime_end"], None if o["value"] == "." else o["value"])
                   for o in ob["observations"]]
    pieces.sort()
    rows: list[list] = []
    for d, rs, re_, v in pieces:
        last = rows[-1] if rows else None
        if (last and last[1] == d and last[4] == v and
                datetime.date.fromisoformat(last[3]) + datetime.timedelta(days=1) == datetime.date.fromisoformat(rs)):
            last[3] = re_                      # same vintage, cut by the window edge
        elif last and last[1] == d and last[2] == rs:
            raise RuntimeError(f"{sid} {d}: two windows both start {rs}")
        else:
            rows.append([sid, d, rs, re_, v])
    return {"series_id": sid, "windows": payloads}, [tuple(r) for r in rows]


def write_observations(cur, rows: list[tuple]) -> None:
    """One series in one statement: COPY into a temp table, then a single
    INSERT ... SELECT, ordered by realtime_start so close_prior_vintage closes
    vintages in sequence, and refresh_series_range (per statement) fires once."""
    cur.execute("CREATE TEMP TABLE IF NOT EXISTS obs_stage (series_id text, observation_date date, "
                "realtime_start date, realtime_end date, value numeric) ON COMMIT DELETE ROWS")
    with cur.copy("COPY obs_stage FROM STDIN") as cp:
        for r in rows:
            cp.write_row(r)
    cur.execute("INSERT INTO observation (series_id, observation_date, realtime_start, realtime_end, value) "
                "SELECT series_id, observation_date, realtime_start, realtime_end, value FROM obs_stage "
                "ORDER BY observation_date, realtime_start "
                "ON CONFLICT (series_id, observation_date, realtime_start) "
                "DO UPDATE SET realtime_end = EXCLUDED.realtime_end, value = EXCLUDED.value")


def load_observations(conn, series_ids: list[str]) -> list[str]:
    """Load every vintage for each series, committing per series so a failure
    (or Ctrl+C) keeps everything loaded so far. Raw payloads go to a new,
    timestamped folder and are never overwritten. Returns the failed ids."""
    run_dir = PAYLOADS / "observations" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest, failed, total, t0 = {}, [], 0, time.monotonic()
    for i, sid in enumerate(series_ids, 1):
        try:
            ob, rows = fetch_observation_rows(sid)
        except RuntimeError as exc:
            failed.append(sid); print(f"[{i}/{len(series_ids)}] {sid}: FAILED {exc}", flush=True)
            continue
        text = json.dumps(ob, indent=1)
        path = run_dir / f"{sid}.json"
        path.write_text(text)
        manifest[path.name] = {"sha256": hashlib.sha256(text.encode()).hexdigest(), "bytes": len(text),
                               "retrieved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with conn.cursor() as cur:
            write_observations(cur, rows)
        conn.commit()
        total += len(rows)
        print(f"[{i}/{len(series_ids)}] {sid}: {len(rows)} vintages  (total {total}, "
              f"{time.monotonic() - t0:.0f}s)", flush=True)
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"observations: {total} rows for {len(series_ids) - len(failed)} series in {run_dir}")
    if failed:
        print(f"failed ({len(failed)}): {' '.join(failed)}")
    return failed


def observations_all(refresh: bool) -> None:
    """Observations for every series already in the catalog (no metadata calls).
    Without --refresh, only series that have no observation rows yet."""
    with psycopg.connect(PG) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT s.series_id FROM series s" + ("" if refresh else
                        " WHERE NOT EXISTS (SELECT 1 FROM observation o WHERE o.series_id = s.series_id)") +
                        " ORDER BY s.popularity DESC NULLS LAST, s.series_id")
            ids = [r[0] for r in cur.fetchall()]
        print(f"{len(ids)} series to load ({'all' if refresh else 'missing only'})", flush=True)
        failed = load_observations(conn, ids)
    raise SystemExit(1 if failed else 0)


# --- documents: agency press releases -> Document / Chunk CSVs (005) ----------
DOC_ROOT = pathlib.Path(os.environ.get("FRED_DOCUMENTS", "data/raw/documents"))
# Press-release PDF location per FRED release id, from the release date.
# Unverified patterns stay out: GDP (53) has no reliable date-based URL yet.
DOC_URLS = {
    50: ("U.S. Bureau of Labor Statistics", "The Employment Situation",
         lambda d: f"https://www.bls.gov/news.release/archives/empsit_{d:%m%d%Y}.pdf"),
    10: ("U.S. Bureau of Labor Statistics", "Consumer Price Index",
         lambda d: f"https://www.bls.gov/news.release/archives/cpi_{d:%m%d%Y}.pdf"),
    13: ("Board of Governors of the Federal Reserve System (US)", "G.17 Industrial Production and Capacity Utilization",
         lambda d: f"https://www.federalreserve.gov/releases/g17/{d:%Y%m%d}/g17.pdf"),
}
CHUNK_CHARS = 800
EMBED_MODEL = "sentence-transformers/all-mpnet-base-v2"   # 768 dims, matches 003


def updates(since: str | None) -> None:
    """Self-updating loop, step one: ask FRED which series changed since the
    watermark (series/updates), keep those in the catalog, refresh their
    metadata, reload their vintages and vintage dates. Idempotent: upserts
    only. The watermark is max(series.last_updated) minus a day unless given
    as --since YYYYMMDDHHMM (FRED's own time, US Central). PostgreSQL only:
    the graph's Series nodes catch up at the next full load (run_all.sh load graph)."""
    with psycopg.connect(PG) as conn:
        with conn.cursor() as cur:
            if since is None:
                cur.execute("SELECT to_char(max(last_updated) - interval '1 day', 'YYYYMMDDHH24MI') FROM series")
                since = cur.fetchone()[0]
            cur.execute("SELECT series_id FROM series")
            catalog = {r[0] for r in cur.fetchall()}
            now = time.strftime("%Y%m%d%H%M")
            up = get("series/updates", start_time=since, end_time=now)
            save(f"series_updates_{since}_{now}", up)
            changed = [s for s in up["seriess"] if s["id"] in catalog]
            print(f"series/updates since {since}: {up.get('count')} series changed in FRED, "
                  f"{len(changed)} of them in the catalog", flush=True)
            # UPDATE, not upsert: PostgreSQL checks NOT NULL before ON CONFLICT, so a
            # partial-column INSERT can never reach the DO UPDATE branch
            cur.executemany("UPDATE series SET title = %s, last_updated = %s, popularity = %s, notes = %s "
                            "WHERE series_id = %s",
                            [(s["title"], s["last_updated"][:19], s.get("popularity"), s.get("notes"), s["id"])
                             for s in changed])
            for s in changed:
                vd = get("series/vintagedates", series_id=s["id"])
                upsert(cur, "vintage_date", ["series_id", "vintage_date"],
                       [(s["id"], d) for d in vd["vintage_dates"]], ["series_id", "vintage_date"])
        conn.commit()
        ids = [s["id"] for s in changed]
        if ids:
            load_observations(conn, ids)
    (PAYLOADS / "manifest.json").write_text(json.dumps(MANIFEST, indent=1))


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Greedy chunks of at most ~size characters, split on word boundaries."""
    words, chunks, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > size:
            chunks.append(cur); cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        chunks.append(cur)
    return chunks


def fetch_document(rid: int, rdate, local_dir: pathlib.Path | None) -> tuple[pathlib.Path | None, str]:
    """Register one press release PDF unchanged under DOC_ROOT/<rid>/<date>.pdf.
    Never overwrites an existing file (raw artifacts are immutable)."""
    dest = DOC_ROOT / str(rid) / f"{rdate:%Y-%m-%d}.pdf"
    if dest.exists():
        return dest, "already registered"
    if local_dir is not None:
        src = local_dir / str(rid) / dest.name
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            return dest, f"copied from {src}"
    url = DOC_URLS[rid][2](rdate)
    ua = os.environ.get("FRED_DOC_USER_AGENT", "fred-catalog-loader/0.1")
    r = requests.get(url, headers={"User-Agent": ua}, timeout=60)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return None, f"HTTP {r.status_code} {r.headers.get('content-type', '')} {url}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest, url


class _PageText(HTMLParser):
    """Visible text of an HTML page: drops script/style/nav/header/footer/aside
    and collapses whitespace. Standard library only."""
    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "svg", "form"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title, self._skip, self._in_title = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self._skip += 1
        if tag == "title": self._in_title = True
        if tag in self.BLOCK: self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip: self._skip -= 1
        if tag == "title": self._in_title = False
        if tag in self.BLOCK: self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title: self.title += data
        elif not self._skip: self.parts.append(data)

    def text(self) -> str:
        t = "".join(self.parts)
        t = "\n".join(" ".join(line.split()) for line in t.splitlines())
        while "\n\n\n" in t: t = t.replace("\n\n\n", "\n\n")
        return t.strip()


def html_text(blob: bytes) -> tuple[str, str]:
    """(title, visible text) of an HTML document; encoding from the bytes."""
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            html = blob.decode(enc); break
        except UnicodeDecodeError:
            continue
    p = _PageText(); p.feed(html); p.close()
    return " ".join(p.title.split()), p.text()


def fetch_page(url: str, dest_stem: pathlib.Path, last_hit: dict) -> tuple[pathlib.Path | None, str, str]:
    """Register the page behind a release_link unchanged as <dest_stem>.html or .pdf.
    One request per second per host; never overwrites. Returns (path, how, file_type)."""
    for ext in ("html", "pdf"):
        dest = dest_stem.with_suffix("." + ext)
        if dest.exists():
            return dest, "already registered", ext
    host = urlsplit(url).netloc
    wait = 1.0 - (time.monotonic() - last_hit.get(host, 0))
    if wait > 0: time.sleep(wait)
    ua = os.environ.get("FRED_DOC_USER_AGENT", "fred-catalog-loader/0.1")
    try:
        r = requests.get(url, headers={"User-Agent": ua, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"},
                         timeout=45, allow_redirects=True)
    except requests.RequestException as e:
        return None, f"{type(e).__name__} {url}", ""
    finally:
        last_hit[host] = time.monotonic()
    if r.status_code != 200:
        return None, f"HTTP {r.status_code} {url}", ""
    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if r.content.startswith(b"%PDF") or ctype == "application/pdf":
        ext = "pdf"
    elif ctype in ("text/html", "application/xhtml+xml") or b"<html" in r.content[:2048].lower():
        ext = "html"
    else:
        return None, f"unsupported content-type {ctype or '?'} {url}", ""
    dest = dest_stem.with_suffix("." + ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest, r.url, ext


def documents(release_ids: list[int], last_n: int, local_dir: pathlib.Path | None, pages: bool = True) -> None:
    """Document layer (graph only, 005). Two kinds of Document per Release:
    press_release_pdf  the agency's dated PDF for each of the last N actual release
                       dates, for releases with a verified URL pattern (DOC_URLS);
    release_page       the page behind FRED's release_link, for every release FRED
                       flags press_release = TRUE (--no-pages to skip). It is the
                       page as it stood after the latest actual release date on or
                       before the fetch, and is keyed by that date, so a rerun after
                       the next release registers a new capture and keeps the old one.
    Raw files are immutable under DOC_ROOT and hashed into DOC_ROOT/manifest.json."""
    from pypdf import PdfReader
    from sentence_transformers import SentenceTransformer

    def pdf_text(path):
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)

    def register(path: pathlib.Path, how: str) -> tuple[str, str]:
        blob = path.read_bytes()
        sha = hashlib.sha256(blob).hexdigest()
        rel = str(path)
        if rel in manifest and manifest[rel]["sha256"] != sha:
            raise RuntimeError(f"{rel} changed on disk since it was registered")
        manifest.setdefault(rel, {"sha256": sha, "bytes": len(blob), "source": how,
                                  "retrieved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        return rel, sha

    def add_doc(doc_id, rid, rdate, kind, ftype, source_name, rel, title, sha, text):
        m = manifest[rel]
        url = m["source"].startswith("http")
        docs.append((doc_id, rid, f"{rdate:%Y-%m-%d}", kind, ftype, source_name, rel, title, sha, m["source"],
                     m["retrieved_at_utc"]))
        n = 0
        for n, piece in enumerate(chunk_text(text), 1):
            chunks.append([doc_id, n - 1, piece])
        print(f"  {doc_id}: {len(text)} chars, {n} chunks ({m['source'] if url else 'local'})", flush=True)

    manifest_path = DOC_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    docs, chunks, failures = [], [], []
    with psycopg.connect(PG) as conn, conn.cursor() as cur:
        for rid in release_ids:
            if rid not in DOC_URLS:
                failures.append(f"release {rid}: no verified press-release URL pattern"); continue
            cur.execute("SELECT release_date FROM release_date WHERE release_id=%s AND date_status='actual' "
                        "ORDER BY release_date DESC LIMIT %s", (rid, last_n))
            dates = [row[0] for row in cur.fetchall()]
            if not dates:
                failures.append(f"release {rid}: no actual release_date rows (run the catalog load first)")
            for rdate in dates:
                path, how = fetch_document(rid, rdate, local_dir)
                if path is None:
                    failures.append(f"release {rid} {rdate}: {how}"); continue
                rel, sha = register(path, how)
                source_name, title, _ = DOC_URLS[rid]
                add_doc(f"fred:release:{rid}:{rdate:%Y-%m-%d}", rid, rdate, "press_release_pdf", "pdf",
                        source_name, rel, f"{title}, {rdate:%B %-d, %Y}", sha, pdf_text(path))
        if pages:
            cur.execute("""
                SELECT r.release_id, r.release_name, r.release_link,
                       (SELECT max(release_date) FROM release_date d
                         WHERE d.release_id = r.release_id AND d.date_status = 'actual'
                           AND d.release_date <= CURRENT_DATE) AS latest,
                       (SELECT string_agg(s.source_name, '; ' ORDER BY s.source_name)
                          FROM release_source rs JOIN source s USING (source_id)
                         WHERE rs.release_id = r.release_id) AS agency
                  FROM release r WHERE r.press_release ORDER BY r.release_id""")
            releases = cur.fetchall()
            print(f"release pages: {len(releases)} releases flagged press_release", flush=True)
            last_hit: dict = {}
            for rid, rname, link, latest, agency in releases:
                if not link:
                    failures.append(f"release {rid} {rname}: press_release but no release_link"); continue
                if latest is None:
                    failures.append(f"release {rid} {rname}: no actual release_date on or before today"); continue
                path, how, ftype = fetch_page(link, DOC_ROOT / str(rid) / f"page_{latest:%Y-%m-%d}", last_hit)
                if path is None:
                    failures.append(f"release {rid} {rname}: {how}"); continue
                rel, sha = register(path, how)
                if ftype == "pdf":
                    title, text = "", pdf_text(path)
                else:
                    title, text = html_text(path.read_bytes())
                if len(text) < 200:
                    failures.append(f"release {rid} {rname}: only {len(text)} chars of text in {rel}"); continue
                add_doc(f"fred:release:{rid}:{latest:%Y-%m-%d}:page", rid, latest, "release_page", ftype,
                        agency or "", rel, title or f"{rname}, release page", sha, text)
        # Every file registered earlier stays a Document: a dated PDF that has left the
        # last-N window, or a page captured for an earlier release date. The CSV is the
        # complete document set, so 005 never leaves a stale node behind.
        cur.execute("""SELECT r.release_id, r.release_name,
                              (SELECT string_agg(s.source_name, '; ' ORDER BY s.source_name)
                                 FROM release_source rs JOIN source s USING (source_id)
                                WHERE rs.release_id = r.release_id) FROM release r""")
        names = {rid: (rname, agency or "") for rid, rname, agency in cur.fetchall()}
        have = {d[0] for d in docs}
        import datetime, re
        for rel in sorted(manifest):
            m = re.fullmatch(re.escape(str(DOC_ROOT)) + r"/(\d+)/(page_)?(\d{4}-\d{2}-\d{2})\.(pdf|html)", rel)
            if not m or int(m[1]) not in names:
                continue
            rid, is_page, dstr, ftype = int(m[1]), bool(m[2]), m[3], m[4]
            doc_id = f"fred:release:{rid}:{dstr}" + (":page" if is_page else "")
            if doc_id in have:
                continue
            path = pathlib.Path(rel)
            if not path.exists():
                failures.append(f"{rel}: in the manifest but missing on disk"); continue
            rdate = datetime.date.fromisoformat(dstr)
            rel, sha = register(path, manifest[rel]["source"])
            rname, agency = names[rid]
            if is_page:
                title, text = ("", pdf_text(path)) if ftype == "pdf" else html_text(path.read_bytes())
                if len(text) < 200:
                    failures.append(f"{rel}: registered earlier but only {len(text)} chars of text"); continue
                add_doc(doc_id, rid, rdate, "release_page", ftype, agency, rel,
                        title or f"{rname}, release page", sha, text)
            else:
                source_name, title = DOC_URLS[rid][:2] if rid in DOC_URLS else (agency, rname)
                add_doc(doc_id, rid, rdate, "press_release_pdf", "pdf", source_name, rel,
                        f"{title}, {rdate:%B %-d, %Y}", sha, pdf_text(path))
            have.add(doc_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=1))
    if chunks:
        model = SentenceTransformer(EMBED_MODEL)
        vecs = model.encode([c[2] for c in chunks], batch_size=32, normalize_embeddings=True,
                            show_progress_bar=False)
        for c, v in zip(chunks, vecs):
            c.append(json.dumps([round(float(x), 6) for x in v]))
    write_csv("documents", ["doc_id", "release_id", "release_date", "kind", "file_type", "source_name", "path",
                            "title", "sha256", "source", "retrieved_at"], docs)
    write_csv("chunks", ["doc_id", "seq", "text", "embedding"], chunks)
    kinds = {k: sum(1 for d in docs if d[3] == k) for k in ("press_release_pdf", "release_page")}
    print(f"documents: {len(docs)} registered ({kinds['press_release_pdf']} dated PDFs, {kinds['release_page']} "
          f"release pages), {len(chunks)} chunks embedded with {EMBED_MODEL}")
    for f in failures:
        print(f"  skipped: {f}")
    print(f"neo4j CSVs: {NEO_IMPORT.resolve()}  (run 005 next)")


# --- full category tree from the MATLAB crawl (Path A) -> PostgreSQL ----------
def category_crawl(path: pathlib.Path) -> None:
    """Upsert every category from fred_category_tree_crawl.m's all_categories.csv
    (CategoryID,Name,ParentID) into PostgreSQL, parents before children.
    No API calls: the crawl's raw responses are already registered on disk."""
    with open(path, newline="") as fh:
        rows = [(int(r["CategoryID"]), r["Name"], int(r["ParentID"])) for r in csv.DictReader(fh)]
    with psycopg.connect(PG) as conn, conn.cursor() as cur:
        cur.execute("SELECT category_id FROM category")
        placed = {r[0] for r in cur.fetchall()}
        if 0 not in placed:  # FRED's root is not a row in the crawl file
            upsert(cur, "category", ["category_id", "category_name", "parent_id"],
                   [(0, "Categories", None)], ["category_id"])
            placed.add(0)
        ordered, pending = [], rows
        while pending:
            level = [r for r in pending if r[2] in placed]
            if not level:
                raise RuntimeError(f"category parents missing for {[r[0] for r in pending][:10]}")
            ordered += level
            placed |= {r[0] for r in level}
            pending = [r for r in pending if r[0] not in placed]
        upsert(cur, "category", ["category_id", "category_name", "parent_id"], ordered, ["category_id"])
        conn.commit()
        cur.execute("SELECT count(*) FROM category")
        print(f"category crawl: {len(rows)} rows from {path}; category table now {cur.fetchone()[0]} rows")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--releases", type=int, nargs="+", default=[50, 10, 53, 13])
    ap.add_argument("--observations", nargs="+", default=["UNRATE", "PAYEMS", "GDPC1", "CPIAUCSL", "INDPRO"])
    ap.add_argument("--max-series", type=int, default=None,
                    help="per release, keep only the N most popular series (plus --observations series); "
                         "the raw release/series payload is still saved in full")
    ap.add_argument("--documents", action="store_true",
                    help="instead of the catalog load, register press-release PDFs for --releases "
                         "and write documents.csv / chunks.csv for 005")
    ap.add_argument("--doc-last", type=int, default=6, help="with --documents: most recent N actual release dates")
    ap.add_argument("--no-pages", action="store_true",
                    help="with --documents: skip the release_link page of every press_release release")
    ap.add_argument("--doc-dir", type=pathlib.Path, default=None,
                    help="with --documents: folder of hand-downloaded PDFs laid out as <release_id>/<YYYY-MM-DD>.pdf")
    ap.add_argument("--category-crawl", type=pathlib.Path, default=None, metavar="CSV",
                    help="instead of the catalog load, upsert the full category tree from the MATLAB "
                         "crawl (data/catalog/fred/crawls/active/all_categories.csv); no API calls")
    ap.add_argument("--observations-all", action="store_true",
                    help="instead of the catalog load, fetch every vintage for each series already in "
                         "the series table that has no observations yet (add --refresh for all)")
    ap.add_argument("--refresh", action="store_true", help="with --observations-all: reload every series")
    ap.add_argument("--no-tables", action="store_true", help="skip release/tables (one call per table element)")
    ap.add_argument("--no-vintages", action="store_true", help="skip series/vintagedates (one call per series)")
    ap.add_argument("--tables-only", action="store_true",
                    help="instead of the catalog load: release/tables for --releases (skipping releases already "
                         "crawled unless --refresh), series/vintagedates for every catalog series, and the CSV")
    ap.add_argument("--series-file", type=pathlib.Path, default=None, metavar="FILE",
                    help="instead of the release walk, catalog the series listed in FILE (first column; e.g. a "
                         "FRED data list saved as data/catalog/fred/lists/*.tsv) and load their vintages")
    ap.add_argument("--updates", action="store_true",
                    help="instead of the catalog load, refresh the catalog series FRED reports as changed "
                         "since the watermark (series/updates) and reload their vintages")
    ap.add_argument("--since", default=None, metavar="YYYYMMDDHHMM",
                    help="with --updates: watermark; default max(series.last_updated) minus one day")
    a = ap.parse_args()
    if a.category_crawl:
        category_crawl(a.category_crawl)
        raise SystemExit(0)
    if a.documents:
        documents(a.releases, a.doc_last, a.doc_dir, not a.no_pages)
        raise SystemExit(0)
    if not KEY:
        raise SystemExit("set FRED_API_KEY")
    if a.series_file:
        series_list(a.series_file, not a.no_vintages, a.refresh)
    if a.updates:
        updates(a.since)
        raise SystemExit(0)
    if a.tables_only:
        with psycopg.connect(PG) as conn:
            tables_and_vintages(conn, a.releases, not a.no_tables, not a.no_vintages, a.refresh)
        (PAYLOADS / "manifest.json").write_text(json.dumps(MANIFEST, indent=1))
        raise SystemExit(0)
    if a.observations_all:
        observations_all(a.refresh)
    main(a.releases, a.observations, a.max_series, tables=not a.no_tables, vintages=not a.no_vintages)
