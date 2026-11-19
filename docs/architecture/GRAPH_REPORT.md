# Graph Report - IUA Attendance  (2026-11-18)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 51 nodes · 121 edges · 7 communities (5 shown, 2 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6

## God Nodes (most connected - your core abstractions)
1. `get_db()` - 13 edges
2. `login_required()` - 11 edges
3. `api_scan()` - 9 edges
4. `export_excel()` - 9 edges
5. `SQLite · students` - 9 edges
6. `reports()` - 8 edges
7. `dashboard()` - 8 edges
8. `SQLite · lectures` - 8 edges
9. `download_qr()` - 7 edges
10. `student_qr()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `recordAttendance()` --POST /api/scan--> `api_scan()`  [EXTRACTED]
  templates/attendance.html → app.py

## Import Cycles
- None detected.

## Communities (7 total, 2 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.24
Nodes (6): attendance_page(), index(), lectures(), login_required(), logout(), students()

### Community 2 - "Community 2"
Cohesion: 0.50
Nodes (3): download_qr(), generate_student_qr(), student_qr_path()

### Community 3 - "Community 3"
Cohesion: 0.53
Nodes (9): api_scan(), dashboard(), export_excel(), get_db(), init_db(), reports(), SQLite · attendance, SQLite · lectures (+1 more)

### Community 5 - "Community 5"
Cohesion: 0.25
Nodes (3): login(), student_qr(), SQLite · users

### Community 6 - "Community 6"
Cohesion: 0.47
Nodes (5): html5-qrcode, onScan(), recordAttendance(), startCamera(), Manual student number

## Knowledge Gaps
- **2 isolated node(s):** `html5-qrcode`, `Manual student number`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 12 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `attendance_page()` connect `Community 0` to `Community 1`, `Community 3`, `Community 6`?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **What connects `html5-qrcode`, `Manual student number` to the rest of the system?**
  _2 weakly-connected nodes found - possible missing edges._
- **Why does `api_scan()` connect `Community 3` to `Community 0`, `Community 1`, `Community 6`?**
  _High betweenness centrality (0.093) - this node is a cross-community bridge._
- **Why does `recordAttendance()` connect `Community 6` to `Community 3`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._