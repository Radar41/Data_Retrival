# ADIT2200 Database Management: ground truth (as of 2026-11-03)

Instructor John Russo. Tue 6:15 to 7:45 PM, Stokes 103N. Canvas course 1686547.
Grading: Discussions 15%, Homework 20%, Quizzes 30%, Term project 35%. A = 94+.
Late policy: homework 10% off up to one week late; project 10% per week up to three weeks; late discussion initial posts still earn credit, late replies do not. In practice Canvas accepted Quiz 2, Quiz 3 and the Week 3 discussion three to four weeks late with full credit, so overdue items remain worth submitting.
Quizzes: two attempts, Canvas keeps the **average** (Quiz 1: 64 and 89 became 76.5). One careful attempt beats two fast ones.

Canvas week numbers run one behind the syllabus topics. This doc uses Canvas weeks.

## Term project (35%): "FRED Metadata Catalog"

Solo (approved; class has ~5 students). Two project descriptions apply: the original class project, and the data-science version (relational core + one semi-structured + one unstructured source + one integrated question). Faculty approved going beyond scope. Neo4j or Memgraph approved for the non-relational layers.

| Stage | Canvas item | Due | Points | Status | What it needs |
|---|---|---|---|---|---|
| 1 Proposal | Week 2: Project Proposal | 9/13 | 10 | **Submitted 10/7, 10/10.** Russo: "looks pretty good. Do you think there will be redundant data?" | Short addendum for the data-science version: name the semi-structured source (FRED API JSON), unstructured source (agency press-release PDFs), how they link (series_id, release_id, release_date), one integrated question. Answer the redundancy comment (see logical design §5). |
| 2 ERD + architecture | Week 4: Assignment Project ERD | 9/27 | 100 | **Built, not submitted.** Rubric: notation 20, entity sets 20, attributes/keys 20, relationships 20, constraints 20. | Submit fred_erd_attributes.png + fred_erd_entities.png + fred_architecture.png. Drawn in Hoffer crow's-foot notation. |
| 3 Relational model + normalization | Week 6: Term Project Assignment | 10/11 | 100 | **Written, not submitted** (fred_logical_design.md) | Relations, FDs, 1NF/2NF/3NF analysis, denormalization reasons, data representation plan for JSON + documents. |
| 4 Physical design | Week 9 Term Project: Physical Design | **Sat 11/8** (moved from 11/1) | 100 | **Written and tested, not submitted** (fred_schema.sql) | Rubric: syntax 30, primary keys 25, foreign keys 25, documentation/comments 20. Script runs clean on PostgreSQL 16; ANSI syntax also valid on MySQL 8. |
| 5 Queries + data | folded into final report | 12/6 | | Written and tested (fred_queries.sql, fred_queries.cypher, fred_triggers.sql, fred_load.py) | Load real FRED data via fred_load.py; run both query sets; capture output. |
| 6 Presentation + report | Week 14: Project Presentation Assignment | 12/6 | | Not started | Report sections listed in project description; recorded presentation. |
| 7 Peer review | Week 15: Presentation Evaluation | 12/6 (Canvas) / wk of 12/14 | | Not started | |

Project files live at `scratchpad/adit2200/fred/` this session and were sent in chat: fred_schema.sql, fred_sample_data.sql, fred_triggers.sql, fred_queries.sql, fred_schema.cypher, fred_queries.cypher, fred_load.py, fred_logical_design.md. Diagrams: fred_erd_attributes.png, fred_erd_entities.png, fred_architecture.png, build_erd.py (Graphviz source).

## Graded homework (20%): eight assignments, 100 pts each

| Canvas item | Prompt (file in project) | Due | Status | Notes |
|---|---|---|---|---|
| Week 3: Graded HW (HW1) | Paul's Popcorn Poppers ERD from entities + 6 business rules; state assumptions | 9/20 | 0/100, not submitted | Lucidchart share or image. Composite + multivalued attributes (addresses, dates of residency), 1:1 customer-account, M:N salesperson-plant, corn-supplier. |
| Week 4: Graded HW (HW2) | Online music company EERD: PERSON supertype, MEMBER/VISITOR subtypes, disjoint, partial; members have ACCOUNT and ORDERS | 9/27 | 0/100, not submitted | Discriminator attribute, "d" in circle, single line (partial). |
| Week 5: Graded HW (HW3) | Antique store order manifest: one relation, PK + FDs, 1NF, 2NF, 3NF with drawings per step | 10/4 | 0/100, not submitted | The prompt file is named "graded homework assignment 4.pdf" but its header says Assignment 3. Classic invoice normalization. |
| Week 6: Graded HW (HW4) | **prompt not in project** (syllabus: functional dependencies and normalization) | 10/11 | 0/100, not submitted | Grab from Canvas. |
| Week 8: Graded HW (HW5) | Shore to Shore Shipping, 6 queries: joins, counts, date arithmetic vs distance table | 11/1 | not submitted | Needs the makship + insert scripts (MySQL versions linked from Week 7 slide 38) and the data-model map. **Not in project.** |
| Week 9: Graded HW (HW6) | Shore to Shore, 5 queries: counts per captain, outer joins for captains/pairs with no shipments, distinct items per origin/destination | 11/1 | not submitted | Submit SQL + results as Word/PDF. Same scripts needed. |
| Week 10: Graded HW (HW7) | **prompt not in project** (syllabus: set operations, CASE, window functions) | 11/8 | upcoming | Practice HW 9 + solutions cover exactly this. |
| Week 12: Graded HW (HW8) | **prompt not in project** (syllabus: triggers, functions, procedures) | 11/22 | upcoming | fred_triggers.sql is a worked example on your own schema. |

Shore to Shore schema (inferred from practice solutions): captain(capt_id, lname, fname, license_grade, dob), ship(ship_no, class, manufacturer_id), manufacturer(manufacturer_id, name), shipment(shipment_id, ship_no, capt_id, origin, destination, shipment_date, arrival_date), shipment_line(shipment_id, item_no, quantity), item(item_no, description, weight, item_type), distance(origin, destination, miles, days).

## Quizzes (30%): Quiz 1 to 13, weekly, due Fridays

Done: Q1 76.5, Q2 100, Q3 100. Open: Q4 (9/25), Q5 (10/2), Q6 (10/9), Q7 (10/23) overdue; Q8 and Q9 (10/30) overdue; Q10 11/6, Q11 11/13, Q12, Q13 upcoming. Style: 8 multiple-choice on the week's reading, 60 to 90 min, 2 attempts averaged.

## Discussions (15%): initial post Thursday, two replies Sunday, 15 pts each

Done: Week 1 (10/15), Week 3 (11/15). Open: Weeks 2, 4, 5, 6 (overdue), Week 7 (10/25, overdue), Week 8 and 9 (11/1, overdue), Week 10 (11/8), then 11, 12, 13, 14, 15. Extra-credit second discussions exist for weeks 1, 3, 4, 5, 6. Adrian writes these himself.

## Materials in the project (what each is for)

- ERD/EERD: chapter 1 to 3 PDFs (Russo supplement), Entity-Relationship Diagramming.txt, Enhanced ERD.txt, Week 3 Lecture Notes (EERD), business case exercises, practice HW 1 to 3 + solutions, Quiz 1 to 3 PDFs.
- Logical design: Week 4 MAPER (ERD to relations, 6 steps, Wilber's Bait World worked example), Week 5 normalize (MacLean & Russo chapter; Passageways Music School example).
- Physical design: Week 6 Lecture (DDL, Oracle syntax, triggers, denormalization, transaction maps), MySQL Physical Design Activity + equipment_checkout starter/solution SQL, practice HW 6 solutions (data types, indexes).
- SQL: Week 7 SQL Part 1 deck, Multiple Table Queries deck (joins, outer joins, ALTER TABLE), aggregation and subqueries decks, practice inner join problems, practice HW 7 to 9 + solutions, Week 8 CASE statement notes.
- Programming: PL/SQL part 1 and 2, triggers.pdf, MySQL Triggers.pdf, Week 10 intro and readings.

## Still missing from Canvas

1. Graded HW 4 prompt (Week 6) and Graded HW 7 prompt (Week 10).
2. Shore to Shore scripts: makship (DDL) and insert (data), MySQL versions, plus the data-model map image.
3. Week 6: Term Project Assignment prompt page (to confirm it is the relational model / normalization stage).
4. Quiz 4 to 9 pages are not needed; they are taken in Canvas.

## Course of action (recorded 2026-11-04)

Method, as agreed with the instructor on Zoom: every homework topic is first worked on the FRED catalog in both PostgreSQL and Neo4j, then the assigned course problem is done as written. The FRED pass is the preamble that shows the concept in the chosen systems; the course problem is the submission. The two never mix in one file.

Framing for the end-of-term discussion: Königsberg. Euler's point was that only the connections matter. In the relational model a connection is stored on one side (the "one" side's key migrates; MAPER steps 3 and 4 decide where), so normalization is partly about where the key lives. In a property graph the connection is its own object, traversed at equal cost either way, so the migration rules and associative tables have no counterpart; FDs still govern properties inside a node. Multiplicity is the trade: Neo4j does not enforce cardinality, so each crow's-foot constraint on the ERD becomes a degree-audit query whose expected answer is zero rows.

| HW | FRED preamble (both stores) | Course submission |
|---|---|---|
| 1 ERD | done: docs/erd | Paul's Popcorn Poppers |
| 2 EERD | Series supertype by frequency or Tag by group, discriminator; Neo4j multi-label `(:Series:Monthly)` | online music company |
| 3, 4 FDs, normalization | docs/design/fred_fd_maps.png and fred_table_map.png; same FDs shown inside a Series node | antique manifest; HW4 prompt still needed |
| 5, 6 joins, outer joins | Q02 to Q05 in both languages; degree audit as the outer-join case | Shore to Shore; makship + insert scripts still needed |
| 7 set ops, CASE, windows | Q07 to Q09; which have no Cypher equivalent and why | HW7 prompt still needed |
| 8 triggers, procedures | sql/fred_triggers.sql; Neo4j has no triggers without APOC | HW8 |

Repo layout to adopt when homework starts: `homework/hwNN_fred/` and `homework/hwNN_submission/`.

Degree audit template (one per ERD relationship, expected result: no rows):
```cypher
MATCH (s:Series) WITH s, count { (s)-[:IN_RELEASE]->() } AS d
WHERE d <> 1 RETURN s.series_id, d
```
