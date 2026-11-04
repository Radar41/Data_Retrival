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
    python fred_load.py --documents --releases 50 13 --doc-last 6     # press releases -> 005 CSVs
    python fred_load.py --category-crawl data/catalog/fred/crawls/active/all_categories.csv

Dependencies: requests, psycopg (v3). Neo4j is loaded from the CSVs by running
003, 004 (and 005) in cypher-shell, so no Neo4j driver is needed here.
"""
import argparse, csv, hashlib, json, os, pathlib, time
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
            # requests' own message embeds the URL, which carries api_key: never surface it
            raise RuntimeError(f"FRED {endpoint}: {type(exc).__name__} (request URL withheld)") from None
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


def get(endpoint: str, **params) -> dict:
    """One FRED call, paged to completion, returned as a single merged payload."""
    params |= {"api_key": KEY, "file_type": "json", "limit": 1000, "offset": 0}
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
        params["offset"] += 1000


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


def main(release_ids: list[int], obs_series: list[str], max_series: int | None = None) -> None:
    with psycopg.connect(PG) as conn, conn.cursor() as cur:
        # --- sources and releases -------------------------------------------------
        sources = get("sources"); save("sources", sources)
        upsert(cur, "source", ["source_id", "source_name", "source_link"],
               [(s["id"], s["name"], s.get("link")) for s in sources["sources"]], ["source_id"])

        releases = get("releases"); save("releases", releases)
        upsert(cur, "release", ["release_id", "release_name", "press_release", "release_link"],
               [(r["id"], r["name"], bool(r["press_release"]), r.get("link")) for r in releases["releases"]],
               ["release_id"])

        rs_payloads, rd_payloads, series_rows, lookups = [], [], [], {"frequency": {}, "units": {}, "sa": {}}
        for rid in release_ids:
            rs = get("release/sources", release_id=rid); rs["release_id"] = rid; rs_payloads.append(rs)
            upsert(cur, "release_source", ["release_id", "source_id"],
                   [(rid, s["id"]) for s in rs["sources"]], ["release_id", "source_id"])

            rd = get("release/dates", release_id=rid, include_release_dates_with_no_data="true"); rd_payloads.append(rd)
            upsert(cur, "release_date", ["release_id", "release_date", "date_status"],
                   [(rid, d["date"], "actual" if d["date"] <= time.strftime("%Y-%m-%d") else "scheduled")
                    for d in rd["release_dates"]], ["release_id", "release_date"])

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

        # --- categories and tags per series ---------------------------------------
        cats, tags_out, cat_rows, tag_rows = {}, [], [], {}
        for (sid, *_rest) in series_rows:
            sc = get("series/categories", series_id=sid); sc["series_id"] = sid; cats[sid] = sc
            for c in sc["categories"]:
                cat_rows.append((c["id"], c["name"], c.get("parent_id")))
            st = get("series/tags", series_id=sid); st["series_id"] = sid; tags_out.append(st)
            for t in st["tags"]:
                tag_rows[t["name"]] = (t["name"], t["group_id"], t.get("notes"), t.get("popularity"))
        save("series_categories", {"items": list(cats.values())}); save("series_tags", {"items": tags_out})

        # walk each category up to the root so every parent_id resolves
        seen = {c[0] for c in cat_rows}
        frontier = {c[2] for c in cat_rows if c[2] is not None and c[2] not in seen}
        while frontier:
            cid = frontier.pop()
            c = get("category", category_id=cid)["categories"][0]
            cat_rows.append((c["id"], c["name"], c.get("parent_id"))); seen.add(c["id"])
            if c.get("parent_id") is not None and c["parent_id"] not in seen and c["parent_id"] != c["id"]:
                frontier.add(c["parent_id"])
        save("categories", {"categories": [{"id": a, "name": b, "parent_id": c} for a, b, c in cat_rows]})
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

        # --- Neo4j catalog CSVs (no observations) ---------------------------------
        write_csv("sources", ["source_id", "source_name", "source_link"],
                  [(s["id"], s["name"], s.get("link") or "") for s in sources["sources"]])
        write_csv("releases", ["release_id", "release_name", "press_release", "release_link"],
                  [(r["id"], r["name"], str(bool(r["press_release"])).lower(), r.get("link") or "") for r in releases["releases"]])
        write_csv("release_sources", ["release_id", "source_id"],
                  [(rs["release_id"], s["id"]) for rs in rs_payloads for s in rs["sources"]])
        write_csv("release_dates", ["release_id", "release_date", "date_status"],
                  [(d["release_id"], d["date"], "actual" if d["date"] <= time.strftime("%Y-%m-%d") else "scheduled")
                   for rd in rd_payloads for d in rd["release_dates"]])
        write_csv("series", ["series_id", "title", "release_id", "frequency_code", "frequency_name", "units_code",
                             "units_name", "sa_code", "sa_name", "observation_start", "observation_end",
                             "last_updated", "popularity", "notes"],
                  [(r[0], r[1], r[2], r[3], lookups["frequency"][r[3]], r[4], lookups["units"][r[4]], r[5],
                    lookups["sa"][r[5]], r[6], r[7], r[8], r[9] or "", r[10] or "") for r in series_rows])
        write_csv("categories", ["category_id", "category_name", "parent_id"],
                  [(a, b, "" if c is None else c) for a, b, c in ordered])
        write_csv("series_categories", ["series_id", "category_id"],
                  [(sid, c["id"]) for sid, sc in cats.items() for c in sc["categories"]])
        write_csv("tag_groups", ["group_id", "group_name"], list(groups.items()))
        write_csv("tags", ["tag_name", "group_id", "tag_notes", "popularity"],
                  [(n, g, nt or "", p if p is not None else "") for n, g, nt, p in tag_rows.values()])
        write_csv("series_tags", ["series_id", "tag_name"],
                  [(st["series_id"], t["name"]) for st in tags_out for t in st["tags"]])

        # --- observations, every vintage (ALFRED), PostgreSQL only ----------------
        for sid in obs_series:
            ob = get("series/observations", series_id=sid, **ALL_VINTAGES); save(f"observations_{sid}", ob)
            rows = [(sid, o["date"], o["realtime_start"], o["realtime_end"],
                     None if o["value"] == "." else o["value"]) for o in ob["observations"]]
            # order by realtime_start so the BEFORE INSERT trigger closes vintages in sequence
            rows.sort(key=lambda r: (r[1], r[2]))
            upsert(cur, "observation", ["series_id", "observation_date", "realtime_start", "realtime_end", "value"],
                   rows, ["series_id", "observation_date", "realtime_start"])
        conn.commit()
    (PAYLOADS / "manifest.json").write_text(json.dumps(MANIFEST, indent=1))
    print(f"loaded {len(series_rows)} series from {len(release_ids)} releases")
    print(f"raw payloads + manifest: {PAYLOADS.resolve()}")
    print(f"neo4j CSVs: {NEO_IMPORT.resolve()}  (run 003 then 004 with :param snapshot_id)")


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


def documents(release_ids: list[int], last_n: int, local_dir: pathlib.Path | None) -> None:
    from pypdf import PdfReader
    from sentence_transformers import SentenceTransformer

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
                blob = path.read_bytes()
                sha = hashlib.sha256(blob).hexdigest()
                rel = str(path)
                if rel in manifest and manifest[rel]["sha256"] != sha:
                    raise RuntimeError(f"{rel} changed on disk since it was registered")
                manifest.setdefault(rel, {"sha256": sha, "bytes": len(blob), "source": how,
                                          "retrieved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                text = "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)
                doc_id = f"fred:release:{rid}:{rdate:%Y-%m-%d}"
                source_name, title, _ = DOC_URLS[rid]
                docs.append((doc_id, rid, f"{rdate:%Y-%m-%d}", "pdf", source_name, rel,
                             f"{title}, {rdate:%B %-d, %Y}", sha))
                for seq, piece in enumerate(chunk_text(text)):
                    chunks.append([doc_id, seq, piece])
                print(f"  {doc_id}: {len(text)} chars, {sum(1 for c in chunks if c[0] == doc_id)} chunks ({how})")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=1))
    if chunks:
        model = SentenceTransformer(EMBED_MODEL)
        vecs = model.encode([c[2] for c in chunks], batch_size=32, normalize_embeddings=True,
                            show_progress_bar=False)
        for c, v in zip(chunks, vecs):
            c.append(json.dumps([round(float(x), 6) for x in v]))
    write_csv("documents", ["doc_id", "release_id", "release_date", "file_type", "source_name", "path", "title", "sha256"], docs)
    write_csv("chunks", ["doc_id", "seq", "text", "embedding"], chunks)
    print(f"documents: {len(docs)} registered, {len(chunks)} chunks embedded with {EMBED_MODEL}")
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
    ap.add_argument("--doc-dir", type=pathlib.Path, default=None,
                    help="with --documents: folder of hand-downloaded PDFs laid out as <release_id>/<YYYY-MM-DD>.pdf")
    ap.add_argument("--category-crawl", type=pathlib.Path, default=None, metavar="CSV",
                    help="instead of the catalog load, upsert the full category tree from the MATLAB "
                         "crawl (data/catalog/fred/crawls/active/all_categories.csv); no API calls")
    a = ap.parse_args()
    if a.category_crawl:
        category_crawl(a.category_crawl)
        raise SystemExit(0)
    if a.documents:
        documents(a.releases, a.doc_last, a.doc_dir)
        raise SystemExit(0)
    if not KEY:
        raise SystemExit("set FRED_API_KEY")
    main(a.releases, a.observations, a.max_series)
