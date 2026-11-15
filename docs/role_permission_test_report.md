# Role Permission and Student-Data Protection Test Report

- **Project:** Student Attendance Management System (SAMS)
- **Issue:** #19 - Test role permissions and student-data protection
- **Branch:** feature/issue-19-role-permission-tests
- **Date:** 15 November 2026
- **Tested against:** SRS SAMS-F-001, F-002, F-005, F-006, F-007, SR-002, SR-003, SR-004, SR-005 (test cases TC-Auth-02, TC-Sec-02, TC-Sec-03, TC-Sec-04, TC-Sec-05)

## 1. Summary

| Item | Result |
|---|---|
| Existing tests before this work | 180 tests, all passing |
| New tests added | 81 (33 in `attendance/test_role_permissions.py`, 48 in `attendance/test_role_data_protection.py`) |
| First run of the new tests | 41 of 48 passed, 7 failed (9 failures counting subtests). All 7 were in `SuspectedDefectTests` |
| Defects found | 5 (D-1 to D-5, with D-3 covering three pages) |
| Defects fixed | 5 |
| Final full run | 261 tests, all passing |
| `python manage.py check` | No issues |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `git diff --check` | No whitespace errors (only CRLF line-ending warnings) |

## 2. Roles and how access is denied

| Role | How it is defined |
|---|---|
| Admin | Active member of the Admin group |
| Superuser | Counts as Admin everywhere |
| Teacher | Member of the Teacher group; sees only sections they are assigned to |
| Student | Member of the Student group; no student-facing pages exist yet |
| No role | Logged-in user in none of the groups |
| Anonymous | Not logged in |

| Situation | What the application does |
|---|---|
| Anonymous user opens a protected page | 302 redirect to `/accounts/login/?next=...` |
| Logged-in user without permission opens an admin, enrollment, report or attendance page | 403 Forbidden |
| Wrong role opens a dashboard | 302 redirect to `/dashboard/` (by design) |
| User without a role opens `/dashboard/` | 403 |
| Unknown ID in the URL | 404 |

## 3. Defects found, fixes and retests

| ID | Defect found | Role affected | SRS | Severity | Fix | File changed | Retest |
|---|---|---|---|---|---|---|---|
| D-1 | `/sessions/<missing id>/mark/` returned a 500 server error | Student, Teacher, Admin | SR-001 | Medium | The missing-session error is turned into a 404 | `attendance/attendance_views.py` | PASS |
| D-2 | `/sessions/<id>/records/` checked the teacher assignment but not the Teacher role | User with an assignment but no Teacher role | SR-004 | Low | Teacher role is now also required | `attendance/correction_views.py` | PASS |
| D-3a | Any Teacher could open the roster of a section they do not teach | Teacher | SR-004 | High | Roster uses the existing `sections_for_user` rule | `attendance/enrollment_views.py` | PASS |
| D-3b | Any Teacher could open any student's enrollment history by changing the ID | Teacher | SR-004 | High | A Teacher only sees history rows from their own sections, otherwise 403 | `attendance/enrollment_views.py` | PASS |
| D-3c | The enrollment section list showed every section to a Teacher | Teacher | SR-004 | Medium | List filtered with `sections_for_user` | `attendance/enrollment_views.py` | PASS |
| D-4 | Logging in without a `next` value redirected to `/accounts/profile/`, which does not exist (404) | All roles | F-001 | Medium | `LOGIN_REDIRECT_URL = '/dashboard/'` | `sams/settings.py` | PASS |
| D-5 | Sessions lasted 2 weeks instead of 30 minutes | All roles | SR-005 | Medium | `SESSION_COOKIE_AGE = 1800` and `SESSION_SAVE_EVERY_REQUEST = True` | `sams/settings.py` | PASS |

The D-3 fix made two older tests fail, because they assumed a Teacher with no section assignment could see every roster. Both only needed their Teacher assigned to a section: `test_teacher_can_view_sections_and_rosters` in `test_enrollment.py` and `test_history_page_shows_all_rows_to_teacher_but_not_student` in `test_transfer_removal.py`. No assertion was removed. Both pass after the update.

## 4. Test results

All results below are from the final run (261 tests, all passing). Rows marked "after fix" failed in the first run and are described in section 3.

### 4.1 Authentication (`test_role_permissions.py`, `test_role_data_protection.py`)

| Scenario | Role | Expected | Actual | Result |
|---|---|---|---|---|
| Open any protected page | Anonymous | Redirect to login | Redirect to `/accounts/login/?next=...` | PASS |
| Open an admin page | Inactive Admin | Treated like anonymous | Redirect to login | PASS |
| Login with `next` value | Admin | Return to the requested page | Redirected to the requested page | PASS |
| Login with wrong password | Any | Not logged in | Login page shown, no session | PASS |
| Login of an inactive account | Inactive user | Not logged in | Login page shown, no session | PASS |
| Open a page after logout | Admin | Redirect to login | Redirect to login | PASS |
| Login without `next` (after fix) | Student | Lands on an existing page | Lands on `/dashboard/` | PASS |
| Session lifetime (after fix) | All | 30 minutes or less | 1800 seconds | PASS |

### 4.2 Dashboards

| Scenario | Role | Expected | Actual | Result |
|---|---|---|---|---|
| Own dashboard | Admin, Teacher, Student | 200 | 200 | PASS |
| Another role's dashboard | Admin, Teacher, Student | Redirect to `/dashboard/` | Redirect to `/dashboard/` | PASS |
| Any dashboard | Superuser | Admin only | Admin dashboard 200, others redirected | PASS |
| `/dashboard/` | Each role | Redirect to own dashboard | As expected | PASS |
| `/dashboard/` and dashboards | No role | 403 / redirect | 403 on `/dashboard/`, redirect on dashboards | PASS |
| Teacher dashboard contents | Teacher | Only own sections | Only own sections listed | PASS |

### 4.3 Account management (`/users/`)

| Scenario | Role | Expected | Actual | Result |
|---|---|---|---|---|
| List, create, edit pages | Anonymous | Redirect to login | Redirect to login | PASS |
| List, create, edit pages | Student, Teacher, no role | 403 | 403 | PASS |
| List, create, edit pages | Admin, Superuser | 200 | 200 | PASS |
| Edit an Admin, superuser, role-less user or unknown ID | Admin | 404 | 404 | PASS |
| POST create or edit account | Student, Teacher, no role | 403 and no data change | 403, no account created or changed | PASS |
| POST create account | Anonymous | Redirect, no data change | Redirect, no account created | PASS |

### 4.4 Teacher assignments (`/teacher-assignments/`)

| Scenario | Role | Expected | Actual | Result |
|---|---|---|---|---|
| List, create, delete pages | Anonymous | Redirect to login | Redirect to login | PASS |
| List, create, delete pages | Student, Teacher, no role | 403 | 403 | PASS |
| List, create pages | Admin, Superuser | 200 | 200 | PASS |
| Teacher assigns themselves a section | Teacher | 403 and no new assignment | 403, no assignment created | PASS |
| POST delete assignment | Student, Teacher, no role | 403 and assignment kept | 403, assignment still exists | PASS |
| POST delete assignment | Anonymous | Redirect, assignment kept | Redirect, assignment still exists | PASS |
| GET on delete URL | Admin | Nothing deleted | Redirect, nothing deleted | PASS |
| POST delete assignment | Admin | Assignment deleted | Deleted | PASS |

### 4.5 Attendance marking (`/sessions/<id>/mark/`)

| Scenario | Role | Expected | Actual | Result |
|---|---|---|---|---|
| Open page | Anonymous | Redirect to login | Redirect to login | PASS |
| Open page | Student, no role | 403 | 403 | PASS |
| Open page for another teacher's section | Unassigned Teacher | 403 | 403 | PASS |
| Open page | Assigned Teacher, Admin, Superuser | 200 | 200 | PASS |
| POST attendance | Unassigned Teacher, Student, no role | 403 and no records | 403, no records created | PASS |
| POST attendance | Anonymous | Redirect, no records | Redirect, no records created | PASS |
| POST attendance | Assigned Teacher | Record saved | Record saved | PASS |
| POST a student from another section | Assigned Teacher | Nothing saved | Nothing saved | PASS |
| POST for a student who already has a record | Assigned Teacher | Existing record unchanged | Unchanged | PASS |
| Open a missing session (after fix) | Student, Teacher, Admin | 403 or 404 | 404 | PASS |

### 4.6 Session records and corrections

| Scenario | Role | Expected | Actual | Result |
|---|---|---|---|---|
| Records page | Anonymous | Redirect to login | Redirect to login | PASS |
| Records page | Student, no role, unassigned Teacher | 403 | 403 | PASS |
| Records page | Assigned Teacher, Admin, Superuser | 200 | 200 | PASS |
| Records page, missing session | Admin | 404 | 404 | PASS |
| Records page with an assignment but no Teacher role (after fix) | Former Teacher | 403 | 403 | PASS |
| Correction page | Anonymous | Redirect to login | Redirect to login | PASS |
| Correction page | Student, no role, unassigned Teacher | 403 | 403 | PASS |
| Correction page | Assigned Teacher, Admin, Superuser | 200 | 200 | PASS |
| Correction page, missing record | Admin | 404 | 404 | PASS |
| POST correction, including a student's own record | Student, unassigned Teacher, no role | 403, record unchanged, no log entry | As expected | PASS |
| POST correction | Anonymous | Redirect, record unchanged | As expected | PASS |
| POST correction | Assigned Teacher | Record changed and logged | Changed, one log entry | PASS |
| POST correction after the 24 hour window | Assigned Teacher | Refused, record unchanged | Form error, record unchanged | PASS |
| Correction service called directly | Student, unassigned Teacher, no role | PermissionDenied | PermissionDenied | PASS |

### 4.7 Enrollment pages (`/enrollments/`)

| Scenario | Role | Expected | Actual | Result |
|---|---|---|---|---|
| Any enrollment page | Anonymous | Redirect to login | Redirect to login | PASS |
| Any enrollment page | Student, no role | 403 | 403 | PASS |
| Section list, roster, history | Teacher | 200 for own sections | 200 | PASS |
| Enroll, transfer, remove | Teacher | 403 | 403 | PASS |
| Every enrollment page | Admin, Superuser | 200 | 200 | PASS |
| GET on remove URL | Admin | 405, nothing changed | 405, enrollment still active | PASS |
| Unknown IDs | Admin | 404 | 404 | PASS |
| POST remove, enroll or transfer | Teacher, Student, no role | 403 and no data change | 403, no enrollment changed | PASS |
| Roster of an unassigned section (after fix) | Teacher | 403 | 403 | PASS |
| History of a student with no enrollment in the Teacher's sections (after fix) | Teacher | 403 | 403 | PASS |
| Section list contents (after fix) | Teacher | Only assigned sections | Only assigned sections | PASS |

### 4.8 Defaulter reports (`/defaulters/`)

| Scenario | Role | Expected | Actual | Result |
|---|---|---|---|---|
| All three pages | Anonymous | Redirect to login | Redirect to login | PASS |
| All three pages | Student, no role | 403 | 403 | PASS |
| Report of an assigned section | Teacher | 200 | 200 | PASS |
| Report of another teacher's section | Teacher | 403 | 403 | PASS |
| Section list contents | Teacher | Only assigned sections | Only assigned sections | PASS |
| Any report | Admin, Superuser | 200 | 200 | PASS |
| Unknown section | Admin | 404 | 404 | PASS |
| Open the threshold settings | Admin, Superuser | 200 | 200 | PASS |
| Open or change the threshold | Teacher, Student, no role | 403, value unchanged | 403, unchanged | PASS |
| Change the threshold | Anonymous | Redirect, value unchanged | Redirect, unchanged | PASS |
| Change the threshold | Admin | Value updated | Updated | PASS |

### 4.9 Direct URL access to student data (12 URLs)

The URLs tested: session records, correction page, mark page, roster, enrollment history and defaulter report, each with an own-section or own-student ID and an other-section or other-student ID.

| Scenario | Role | Expected | Actual | Result |
|---|---|---|---|---|
| All 12 URLs | Anonymous | Redirect to login | Redirect to login | PASS |
| All 12 URLs, own IDs and other students' IDs | Student, another Student, no role | 403 | 403 | PASS |
| Records, correction, mark and defaulter pages of another teacher's section | Teacher | 403 | 403 | PASS |
| All 12 URLs | Admin | 200 | 200 | PASS |

## 5. Not covered by these tests

| Area | Reason |
|---|---|
| Student view of their own attendance (SRS 2.3, SAMS-F-011) | No such page exists yet. `/dashboard/student/` only returns the text "Student Dashboard". The tests confirm students are refused on every other student-data URL |
| Leave requests (Issue #18, SAMS-F-015) | Not merged yet (PR #43). Permission tests should be added after the merge, in particular "unauthorized users cannot change request decisions" |
| Report export (SAMS-F-013) and low-attendance alerts (SAMS-F-014) | No URLs exist in the project |
| Django admin site (`/admin/`) and Django's built-in login, logout and password pages (`/accounts/`) | Built-in Django features, not part of the SAMS code |
| Live session expiry | D-5 is checked through the setting (`SESSION_COOKIE_AGE`), not by waiting 30 minutes |

## 6. Observations (not defects)

1. **Two copies of the admin check.** `is_sams_admin` in `attendance/permissions.py` and `has_role` in `attendance/views.py` do the same job. They behave the same today, but a future change to one could leave the other behind.
2. **Role checks are not applied the same way on every page.** The defaulter, correction and marking pages check both the Teacher role and the section assignment. Before the fixes, two pages checked only one of the two (see D-2 and D-3).
3. **SRS SR-002 and the code differ slightly.** The SRS says only "the marking Teacher or an Admin" may correct a record. The code allows any Teacher assigned to that section, which matches SAMS-F-005 (several teachers per section).
4. **404 versus 403.** An unknown ID gives a 404 and an existing but forbidden ID gives a 403, so a logged-in user can tell which IDs exist. This is normal Django behaviour and low risk.
5. **The enrollment history page now filters by section.** A Teacher sees only the enrollment rows from sections they teach. If a student was transferred out of the Teacher's section, the Teacher no longer sees the rows from the other section.

## 7. Files changed for Issue #19

| File | Change |
|---|---|
| `attendance/test_role_permissions.py` | New: 33 tests (accounts, dashboards, teacher assignments, defaulter reports) |
| `attendance/test_role_data_protection.py` | New: 48 tests (login, attendance, corrections, enrollment, student-data protection, defect checks) |
| `attendance/attendance_views.py` | Fix D-1 |
| `attendance/correction_views.py` | Fix D-2 |
| `attendance/enrollment_views.py` | Fix D-3 |
| `sams/settings.py` | Fixes D-4 and D-5 |
| `attendance/test_enrollment.py` | One old test: Teacher assigned to a section first |
| `attendance/test_transfer_removal.py` | One old test: Teacher assigned to both sections first |
| `docs/role_permission_test_report.md` | New: this report |

## 8. How to re-run

    python manage.py test attendance.test_role_permissions attendance.test_role_data_protection
    python manage.py test
    python manage.py check
    python manage.py makemigrations --check --dry-run
    git diff --check
