# Regression Test Report - Issue #23

- **Project:** Student Attendance Management System (SAMS)
- **Issue:** #23 - Create automated tests and regression test suite
- **Branch:** feature/issue-23-regression-test-suite (created from `main` at `1d77e97`, the merge of PR #47)
- **Date:** 16 November 2026
- **Environment:** Windows, PowerShell, Python 3.14, Django 6.1.x, SQLite
- **How to run the tests:** see `docs/testing.md`

## 1. Summary

| Item | Result |
|---|---|
| Tests before this work (current `main`) | 339 tests, all passing (`Ran 339 tests in 573.724s`, OK) |
| New tests added | 37: 24 in `attendance/test_courses.py`, 12 in `attendance/test_attendance_services.py` (class `AttendanceBoundaryTests`), 1 in `attendance/test_regression_workflow.py` |
| Final full run | 376 tests, all passing (`Ran 376 tests in 615.075s`, OK) |
| Issue #15 defaulter tests (`test_defaulters`, 17 tests) | Unchanged and included in the full run, all passing |
| Application code changed | None. Only test files and documentation were added or extended |
| Defects found by the new tests | None |
| `python manage.py check` | No issues (0 silenced) |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `git diff --check` and new-file whitespace scan | No whitespace errors in the modified file; no trailing whitespace in the three new files |

## 2. Scenarios, expected and actual results

"Actual" is what the full run of 376 tests reported. Every row below passed.

| Area | Scenario | Expected | Actual | Result | Tests |
|---|---|---|---|---|---|
| A. Authentication | Login with valid credentials | User is logged in | As expected | PASS | `tests`, `test_role_data_protection` (existing) |
| A. Authentication | Wrong password, or inactive account | User is not logged in | As expected | PASS | `tests`, `test_role_data_protection` (existing) |
| A. Authentication | Anonymous user opens a protected page | Redirected to the login page with `next` | As expected | PASS | `test_role_data_protection`, `test_enrollment`, `test_reports` (existing) |
| A. Authentication | Logout | Protected pages are no longer reachable | As expected | PASS | `test_role_data_protection` (existing) |
| B. Roles | Admin, Teacher, Student, no role and anonymous open each page | Allowed pages open; others give 403 or a redirect | As expected | PASS | `test_role_permissions` 33, `test_role_data_protection` 48, `test_role_new_features` 34, `test_security` 6 (existing) |
| C. Courses | Blank, over-long or duplicate course code and name | Rejected by validation or by the database | As expected | PASS | `test_courses` 24 (new) |
| C. Courses | Update course details; section and schedule rules | Update is saved; duplicate, blank and overlapping data rejected | As expected | PASS | `test_courses`, `tests` (new and existing) |
| D. Enrollment | Enroll, duplicate, only active students, roster, remove, re-enroll | Valid enrollments saved; invalid or duplicate ones refused | As expected | PASS | `test_enrollment` 29, `test_transfer_removal` 23 (existing) |
| E. Attendance | Assigned teacher marks attendance; others refused; bad student or status rejected; no overwrite | Only valid, authorised submissions are saved | As expected | PASS | `test_attendance_submission` 7, `test_role_data_protection` (existing) |
| E. Attendance | Teacher corrects a record | Record and history updated | As expected | PASS | `test_corrections` 20 (existing) |
| F. Calculation | Present and Late count as attended; no records; invalid status ignored; enrollment dates respected | Correct percentage, or no percentage when there are no records | As expected | PASS | `test_attendance_services`, 6 existing tests |
| F. Calculation | Boundaries: exactly 75.0, 74.07, 75.68, rounding to 66.67, all Late = 100, enrollment end day counted, day after not counted, gap between two enrollments, date range edges, other students and sections ignored | Percentages and counts as listed | As expected | PASS | `test_attendance_services`, 12 new tests |
| G. Reports | CSV content, date range, section access, no data | Report matches the calculation; unauthorised users refused | As expected | PASS | `test_reports` 18 (existing) |
| G. Reports | Defaulter list: threshold change, exact threshold, record changes | List follows the calculation and the threshold | As expected | PASS | `test_defaulters` 17 (existing, Issue #15) |
| H. End to end | Admin enrolls, teacher marks, percentages, defaulter list, CSV, correction, student refused | Every step agrees with the others | As expected | PASS | `test_regression_workflow` 1 (new) |
| I. Reliability | Performance, concurrency, session expiry | Existing expectations met | As expected | PASS | `test_performance` 4, `test_concurrency` 3, `test_session_reliability` 4 (existing) |

## 3. Defects found

None. The course and calculation tests passed when first run on the project machine (42 tests in `test_courses` and `test_attendance_services`), and the full run of 376 tests, which includes the end-to-end test, passed.

Observations that are not defects:

- **O-1:** SAMS has no screens for creating or editing courses, sections, schedules, teacher assignments or attendance sessions, and `Course` is not registered in the Django admin. Course rules are tested at model level, so "unauthorised users cannot modify courses" cannot be tested through the web.
- **O-2:** The full suite took about 10 minutes on the project machine. The cause has not been profiled (`--durations 10` lists the slowest tests).
- **O-3:** The local copy of `main` was 47 commits behind `origin/main` when this work started, so it was updated by fast-forward before any test was written.

## 4. Fixes made

None. No application code was changed for Issue #23.

## 5. Retest outcome

After all new test files were added, the complete suite was run once more: 376 tests, OK. `docs/testing.md` and this report were written afterwards and do not affect the tests.

## 6. Verification notes

- The new tests were also checked for effectiveness in a separate copy of the project (not this repository): LATE counting was deliberately broken and `test_full_attendance_workflow` failed (`50.0 != 75.0`). The change was then reverted.
- An earlier baseline run on a Linux copy of the same `main` also passed all 339 tests.

## 7. Repeating the run

```powershell
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
git --no-pager diff --check
```
