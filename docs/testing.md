# Testing SAMS

This guide explains how to run the automated test suite for the Student
Attendance Management System (SAMS), how to read the results, and what the
tests cover. It was written for Issue #23 (automated tests and regression
test suite). For the results of a specific test run, see
`docs/regression_test_report.md`.

## 1. Prerequisites and setup

- Python 3 and Django. The project has no `requirements.txt`; install Django
  with `pip install django`. The suite has been run on Windows (Python 3.14,
  Django 6.1.x) and on Linux (Python 3.12, Django 6.1.3).
- Open a terminal in the project folder (the one that contains `manage.py`).
- A virtual environment is optional. If you use one:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install django
```

- No database setup is needed. Django builds a separate temporary test
  database (`test_db.sqlite3`, set in `sams/settings.py`) and deletes it when
  the run finishes. The real `db.sqlite3` is never touched by the tests.

## 2. Run all tests

```powershell
python manage.py test
```

This is the command to run before a release or after any change. At the time
of writing it runs 376 tests. The run is slow on some machines (about 10
minutes on one Windows computer, about 80 seconds on a Linux server).

To run everything except the three timing-sensitive modules
(performance, concurrency, session reliability), use this quicker command.
It currently runs 365 tests:

```powershell
python manage.py test attendance.tests attendance.test_attendance_services attendance.test_attendance_submission attendance.test_corrections attendance.test_courses attendance.test_defaulters attendance.test_enrollment attendance.test_leave_requests attendance.test_regression_workflow attendance.test_reports attendance.test_role_data_protection attendance.test_role_new_features attendance.test_role_permissions attendance.test_security attendance.test_teacher_assignment attendance.test_transfer_removal attendance.test_user_accounts
```

## 3. Run one test module

```powershell
python manage.py test attendance.test_defaulters
python manage.py test attendance.test_courses attendance.test_attendance_services
```

Use the module name without `.py`. You can list several modules in one command.

## 4. Run one test case or one test

```powershell
python manage.py test attendance.test_defaulters.DefaulterServiceTests
python manage.py test attendance.test_defaulters.DefaulterServiceTests.test_default_threshold_is_75
```

The pattern is `attendance.<module>.<TestClass>.<test_method>`.

Useful options:

| Option | What it does |
|---|---|
| `-v 2` | Prints the name of every test and whether it passed |
| `--failfast` | Stops at the first failure |
| `--durations 10` | Lists the 10 slowest tests (needs Python 3.12 or newer) |

## 5. How to read the results

While running, each test prints one character:

| Character | Meaning |
|---|---|
| `.` | The test passed |
| `F` | Failure: the code ran, but a check (assertion) did not match |
| `E` | Error: the test crashed before it could finish |

The run ends with a summary:

- `Ran 376 tests in ...` followed by `OK` means every test passed.
- `FAILED (failures=2, errors=1)` means something needs attention. Each
  problem is printed above the summary with the test name and a traceback.
- Some performance tests print extra lines such as
  `[120 students] first submit: ...`. These are timing information, not errors.
- Messages such as `Destroying old test database` are normal.

## 6. Investigating a failure

1. Read the traceback from the bottom up. The last lines show the failing
   check, for example `AssertionError: 50.0 != 75.0` (the first value is what
   the code returned, the second is what the test expected).
2. The traceback also names the test file and line number. Open that test and
   read what it sets up and what it expects.
3. Run just that test again with `-v 2` (see section 4) to confirm it is
   repeatable.
4. Decide whether the code or the test is wrong. If the code is wrong, fix it
   and re-run the whole suite. If the behaviour was changed on purpose, update
   the test and say why in the commit message.
5. If a run was interrupted and the next run complains that the test database
   already exists or is locked, delete only `test_db.sqlite3`. Never delete
   `db.sqlite3` or the `db_before_*` backup files.
6. Record any defect you cannot fix straight away in the regression test
   report so it is visible before release.

## 7. Critical workflows covered

| Workflow | Test modules | Tests |
|---|---|---|
| Authentication: login, bad login, logout, anonymous redirects, sessions | `tests`, `test_role_data_protection`, `test_session_reliability` | included in rows below |
| Account management | `test_user_accounts` | 47 |
| Role permissions and student-data protection (Admin, Teacher, Student, no role, anonymous) | `test_role_permissions`, `test_role_data_protection`, `test_role_new_features`, `test_security` | 33, 48, 34, 6 |
| Courses, sections, schedules | `tests` (17 tests, includes basic course/section/schedule rules), `test_courses` | 24 in `test_courses` |
| Enrollment, transfer, removal, teacher assignment | `test_enrollment`, `test_transfer_removal`, `test_teacher_assignment` | 29, 23, 8 |
| Attendance sessions, marking, corrections | `tests`, `test_attendance_submission`, `test_corrections` | 7, 20 |
| Attendance calculation (Present/Late/Absent, percentages, boundaries, enrollment periods) | `test_attendance_services` | 18 |
| Reports and CSV export | `test_reports` | 18 |
| Defaulter list (Issue #15) | `test_defaulters` | 17 |
| Leave requests | `test_leave_requests` | 15 |
| Performance, concurrency, session reliability | `test_performance`, `test_concurrency`, `test_session_reliability` | 4, 3, 4 |
| End-to-end regression workflow | `test_regression_workflow` | 1 |

The end-to-end test follows one path through the real login page and views:
admin enrolls students, teacher marks attendance, percentages are calculated,
the defaulter list and CSV report agree, a teacher corrects a record, and
everything updates.

## 8. Known limitations and outstanding defects

- SAMS has no screens for creating or editing courses, sections, schedules,
  teacher assignments or attendance sessions, and `Course` is not registered
  in the Django admin. These are tested at model level (validation and saving),
  and tests create such records directly in the database. Access restrictions
  for "modifying courses" cannot be tested through the web until those screens
  exist.
- The tests use SQLite only and do not include browser-based interface tests.
- No test-coverage measurement tool is set up, so coverage is judged by the
  workflows listed above, not by a percentage.
- The long run time on slower machines has not been profiled. Use
  `--durations 10` to see which tests are slowest.
- Outstanding defects: none were found by the Issue #23 tests, and no
  application code was changed for Issue #23.
