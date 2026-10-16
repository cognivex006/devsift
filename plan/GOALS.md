# DevSift v6 — Goal Catalog

2026-10-16 sessions: **G000–G005 accepted** (17 tasks); evidence in `docs/evidence/` and canonical status in `plan/ledger.json`.

26 goals / 77 tasks. Goal timebox <=165 active minutes including review and checkpoint. Recompute structural class from actual transitive task dependencies.

|Canonical|Execution|Class|Goal outcome|Tasks|True entries|
|---|---|---|---|---|---|
|G000|GA000|A|DevSift repository first bootstrap and verification|T000, T076|T000|
|G001|GA001|A|Policy contract and classification|T001, T002, T003|T001, T002|
|G002|GA002|A|CLI shell and exit contracts|T004, T005, T006|T004, T005|
|G003|GA003|A|Evidence and location schema|T007, T008, T009|T007, T008|
|G004|GA004|A|Scanning core and adapters|T010, T011, T012|T010, T011|
|G005|GA005|A|Git change classification|T013, T014, T015|T013|
|G006|GA006|A|Legacy baseline and suppressions|T016, T017, T018|T016, T017|
|G007|GA007|A|Analyzer host / plugins|T019, T020, T021|T019|
|G008|GA008|A|Backend .NET and Go|T022, T023, T024|T022|
|G009|GA009|A|Frontend TypeScript|T025, T026, T027|T025|
|G010|GA010|A|SQL static analysis|T028, T029, T030|T028|
|G011|GA011|A|Security rules and sanitization|T031, T032, T033|T031|
|G012|GA012|A|Observability recommendation rules|T034, T035, T036|T034|
|G013|GB013|B|Source-aware Markdown and SARIF reports|T037, T038, T039|T037|
|G014|GB014|B|Impact/legacy decisions in reports|T040, T041, T042|T040, T041|
|G015|GB015|B|CI quality gate and PR workflow|T043, T044, T045|T043|
|G016|GB016|B|Agent review and remediation skill|T046, T047, T048|T046|
|G017|GB017|B|Cross-language integration and regression|T049, T050, T051|T049, T050|
|G018|GB018|B|Package build and installation|T052, T053, T054|T052|
|G019|GA019|A|Agent governance and documentation|T055, T056, T057|T055|
|G020|GA020|A|Doctor and diagnostics|T058, T059, T060|T058|
|G021|GA021|A|Regression-safe remediation protections|T061, T062, T063|T061|
|G022|GA022|A|Multirepo ownership and policy overrides|T064, T065, T066|T064|
|G023|GB023|B|Security release gate hardening|T067, T068, T069|T067|
|G024|GB024|B|Open-source publication readiness|T070, T071, T072|T070|
|G025|GA025|A|Developer experience and guide|T073, T074, T075|T073, T074|

## Group A — 18 goals
- **GA000 (G000)** DevSift repository first bootstrap and verification. T000 requires none; full gates=none; partial=none
- **GA001 (G001)** Policy contract and classification. T001 requires ['T000']; full gates=none; partial={'G000': ['T000']}; T002 requires ['T000']; full gates=none; partial={'G000': ['T000']}
- **GA002 (G002)** CLI shell and exit contracts. T004 requires ['T000']; full gates=none; partial={'G000': ['T000']}; T005 requires ['T000']; full gates=none; partial={'G000': ['T000']}
- **GA003 (G003)** Evidence and location schema. T007 requires ['T000']; full gates=none; partial={'G000': ['T000']}; T008 requires ['T000']; full gates=none; partial={'G000': ['T000']}
- **GA004 (G004)** Scanning core and adapters. T010 requires ['T000', 'T001']; full gates=none; partial={'G000': ['T000'], 'G001': ['T001']}; T011 requires ['T000', 'T004']; full gates=none; partial={'G000': ['T000'], 'G002': ['T004']}
- **GA005 (G005)** Git change classification. T013 requires ['T000', 'T007']; full gates=none; partial={'G000': ['T000'], 'G003': ['T007']}
- **GA006 (G006)** Legacy baseline and suppressions. T016 requires ['T000', 'T007', 'T013']; full gates=none; partial={'G000': ['T000'], 'G003': ['T007'], 'G005': ['T013']}; T017 requires ['T000', 'T002']; full gates=none; partial={'G000': ['T000'], 'G001': ['T002']}
- **GA007 (G007)** Analyzer host / plugins. T019 requires ['T000', 'T001', 'T010']; full gates=none; partial={'G000': ['T000'], 'G001': ['T001'], 'G004': ['T010']}
- **GA008 (G008)** Backend .NET and Go. T022 requires ['T000', 'T001', 'T010', 'T019']; full gates=none; partial={'G000': ['T000'], 'G001': ['T001'], 'G004': ['T010'], 'G007': ['T019']}
- **GA009 (G009)** Frontend TypeScript. T025 requires ['T000', 'T001', 'T010', 'T019']; full gates=none; partial={'G000': ['T000'], 'G001': ['T001'], 'G004': ['T010'], 'G007': ['T019']}
- **GA010 (G010)** SQL static analysis. T028 requires ['T000', 'T001', 'T010', 'T019']; full gates=none; partial={'G000': ['T000'], 'G001': ['T001'], 'G004': ['T010'], 'G007': ['T019']}
- **GA011 (G011)** Security rules and sanitization. T031 requires ['T000', 'T001', 'T010', 'T019']; full gates=none; partial={'G000': ['T000'], 'G001': ['T001'], 'G004': ['T010'], 'G007': ['T019']}
- **GA012 (G012)** Observability recommendation rules. T034 requires ['T000', 'T001', 'T008', 'T010', 'T019']; full gates=none; partial={'G000': ['T000'], 'G001': ['T001'], 'G003': ['T008'], 'G004': ['T010'], 'G007': ['T019']}
- **GA019 (G019)** Agent governance and documentation. T055 requires ['T000', 'T001']; full gates=none; partial={'G000': ['T000'], 'G001': ['T001']}
- **GA020 (G020)** Doctor and diagnostics. T058 requires ['T000', 'T004']; full gates=none; partial={'G000': ['T000'], 'G002': ['T004']}
- **GA021 (G021)** Regression-safe remediation protections. T061 requires ['T000', 'T007', 'T013']; full gates=none; partial={'G000': ['T000'], 'G003': ['T007'], 'G005': ['T013']}
- **GA022 (G022)** Multirepo ownership and policy overrides. T064 requires ['T000', 'T001']; full gates=none; partial={'G000': ['T000'], 'G001': ['T001']}
- **GA025 (G025)** Developer experience and guide. T073 requires ['T000', 'T001']; full gates=none; partial={'G000': ['T000'], 'G001': ['T001']}; T074 requires ['T000', 'T007', 'T008', 'T009', 'T037', 'T038', 'T039']; full gates=['G003', 'G013']; partial={'G000': ['T000']}

## Group B — 8 goals
- **GB013 (G013)** Source-aware Markdown and SARIF reports. T037 requires ['T000', 'T007', 'T008', 'T009']; full gates=['G003']; partial={'G000': ['T000']}
- **GB014 (G014)** Impact/legacy decisions in reports. T040 requires ['T000', 'T002', 'T007', 'T013', 'T016', 'T017', 'T018']; full gates=['G006']; partial={'G000': ['T000'], 'G001': ['T002'], 'G003': ['T007'], 'G005': ['T013']}; T041 requires ['T000', 'T007', 'T008', 'T009', 'T037', 'T038', 'T039']; full gates=['G003', 'G013']; partial={'G000': ['T000']}
- **GB015 (G015)** CI quality gate and PR workflow. T043 requires ['T000', 'T004', 'T005', 'T006']; full gates=['G002']; partial={'G000': ['T000']}
- **GB016 (G016)** Agent review and remediation skill. T046 requires ['T000', 'T007', 'T008', 'T009', 'T037']; full gates=['G003']; partial={'G000': ['T000'], 'G013': ['T037']}
- **GB017 (G017)** Cross-language integration and regression. T049 requires ['T000', 'T001', 'T007', 'T010', 'T019', 'T020', 'T021', 'T022', 'T023', 'T024']; full gates=['G007', 'G008']; partial={'G000': ['T000'], 'G001': ['T001'], 'G003': ['T007'], 'G004': ['T010']}; T050 requires ['T000', 'T001', 'T010', 'T019', 'T025', 'T026', 'T027', 'T028', 'T029', 'T030']; full gates=['G009', 'G010']; partial={'G000': ['T000'], 'G001': ['T001'], 'G004': ['T010'], 'G007': ['T019']}
- **GB018 (G018)** Package build and installation. T052 requires ['T000', 'T001', 'T002', 'T004', 'T005', 'T006', 'T007', 'T008', 'T009', 'T010', 'T013', 'T016', 'T017', 'T018', 'T019', 'T020', 'T021', 'T022', 'T023', 'T024', 'T025', 'T026', 'T027', 'T028', 'T029', 'T030', 'T031', 'T032', 'T033', 'T034', 'T035', 'T036', 'T037', 'T038', 'T039', 'T040', 'T041', 'T042', 'T043', 'T044', 'T045', 'T046', 'T047', 'T048', 'T049', 'T050', 'T051']; full gates=['G002', 'G003', 'G006', 'G007', 'G008', 'G009', 'G010', 'G011', 'G012', 'G013', 'G014', 'G015', 'G016', 'G017']; partial={'G000': ['T000'], 'G001': ['T001', 'T002'], 'G004': ['T010'], 'G005': ['T013']}
- **GB023 (G023)** Security release gate hardening. T067 requires ['T000', 'T001', 'T010', 'T019', 'T031', 'T032', 'T033']; full gates=['G011']; partial={'G000': ['T000'], 'G001': ['T001'], 'G004': ['T010'], 'G007': ['T019']}
- **GB024 (G024)** Open-source publication readiness. T070 requires ['T000', 'T001', 'T002', 'T004', 'T005', 'T006', 'T007', 'T008', 'T009', 'T010', 'T013', 'T016', 'T017', 'T018', 'T019', 'T020', 'T021', 'T022', 'T023', 'T024', 'T025', 'T026', 'T027', 'T028', 'T029', 'T030', 'T031', 'T032', 'T033', 'T034', 'T035', 'T036', 'T037', 'T038', 'T039', 'T040', 'T041', 'T042', 'T043', 'T044', 'T045', 'T046', 'T047', 'T048', 'T049', 'T050', 'T051', 'T052', 'T053', 'T054', 'T067', 'T068', 'T069']; full gates=['G002', 'G003', 'G006', 'G007', 'G008', 'G009', 'G010', 'G011', 'G012', 'G013', 'G014', 'G015', 'G016', 'G017', 'G018', 'G023']; partial={'G000': ['T000'], 'G001': ['T001', 'T002'], 'G004': ['T010'], 'G005': ['T013']}

## Bootstrap handoff

1. **T000 (GA000)** is the sole initial ready task. Its deliverable is a remote GitHub bootstrap commit and repository Description, not product code.
2. **T076 (GA000)** becomes eligible only after T000 accepted; existing T001/T002/T004/T005/T007/T008 also unlock on T000 accepted, without waiting for G000 to close.
3. In-review does not unlock; eligibility still requires locks, actual capacity, branch ownership, accepted evidence and current remote state.
4. Do not dispatch optional out-of-scope work to fill slots.
