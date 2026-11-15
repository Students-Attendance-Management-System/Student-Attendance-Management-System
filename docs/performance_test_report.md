# Attendance Submission Performance and Reliability Report (Issue #20)

## Environment
- Django 6.1.2, SQLite (file database), Windows, Django test client (no network latency)
- Tests: `attendance/test_performance.py`, `attendance/test_concurrency.py`
- Run with: `python manage.py test attendance.test_performance attendance.test_concurrency`

## 1. Response time (one teacher submits a whole class)

| Class size | First submit | Repeat submit | Rows saved |
|---|---|---|---|
| 30 | 173 ms | 14 ms | 30 |
| 60 | 323 ms | 19 ms | 60 |
| 120 | 686 ms | 58 ms | 120 |
| 200 | 1016 ms | 28 ms | 200 |

Response time grows linearly, about 5 ms per student, because `submit_attendance` calls
`get_or_create` once per student. No failures at any size. A repeat submit is fast
because no new rows are written.

## 2. Concurrency and duplicates

| Scenario | Result |
|---|---|
| 5 simultaneous submits of the same session (all PRESENT) | All 302, 30/30 rows, no duplicates |
| 5 simultaneous submits of the same session (all ABSENT, exercises alert creation) | All 302, 30/30 rows, 30 alerts (one per student) |
| 8 teachers submitting 8 different sessions at once | All 302, 30 rows in each session |

Duplicate prevention works: the `unique_student_attendance_per_session` constraint plus
`get_or_create` inside `transaction.atomic` never produced a duplicate or lost record.

## 3. Defects

| # | Defect | Severity | Status |
|---|---|---|---|
| 1 | With default SQLite settings, concurrent submits failed with `database is locked` (HTTP 500). 7 of 8 teachers saved 0 rows. Cause: `atomic` starts a read transaction, and SQLite refuses the upgrade to a write instantly instead of waiting. | High | Fixed in `sams/settings.py` (`timeout: 30`, `transaction_mode: IMMEDIATE`). Retested: all submits succeed. |
| 2 | Repeating a submit that had already succeeded showed the error "No attendance data was submitted". No duplicates were created. | Low (UX) | Fixed in `attendance_views.py`: if every student already has a record, show an info message and redirect. Retested. |

## 4. Limitations
- All results are from SQLite. Under MySQL or PostgreSQL, locking behaves differently and the
  concurrency tests should be rerun. The alert race (`refresh_section_alerts`) in particular
  is only verified on SQLite.
- Load comes from the Django test client on one machine, so network latency and real browser
  behavior are not measured.
- SQLite allows one writer at a time. Many teachers submitting in the same instant queue up,
  which is acceptable at this scale but would not scale to a large institution.
