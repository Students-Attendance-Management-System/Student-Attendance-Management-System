# Attendance Performance, Concurrency and Usability Test Report (Issues #20 and #21)

## 1. Objective

Evaluate attendance submission performance, concurrent-user behavior, report generation and usability of the Student Attendance Management System (SAMS).

The evaluation covers automated workflow tests, concurrent submissions, report accuracy, performance measurements and documented limitations.

## 2. Test Environment

- Framework: Django 6.1.2
- Database: SQLite (file database)
- Operating system: Windows
- Testing method: Django automated test suite and test client
- Performance tests: `attendance/test_performance.py`
- Concurrency tests: `attendance/test_concurrency.py`
- Report tests: `attendance/test_reports.py`

## 3. Attendance Submission Performance

Attendance submission was measured with different class sizes.

| Class size | First submission | Repeat submission | SQL queries | Rows saved |
|---|---:|---:|---:|---:|
| 30 students | 77 ms | 7 ms | 208 | 30 |
| 60 students | 153 ms | 9 ms | 388 | 60 |
| 120 students | 310 ms | 12 ms | 748 | 120 |
| 200 students | 500 ms | 17 ms | 1,228 | 200 |

### Observations

- All four performance tests passed.
- All expected attendance records were saved.
- Submission time increased with class size.
- Repeat submissions were faster because existing records were not duplicated.
- SQL query count increased with the number of students.

## 4. Concurrent-User Testing

Three concurrency scenarios were tested.

| Scenario | Result |
|---|---|
| Five simultaneous submissions for the same session (all PRESENT) | All 5 returned HTTP 302; exactly 30 records saved |
| Five simultaneous submissions for the same session (all ABSENT) | All 5 returned HTTP 302; 30 records and 30 alerts created |
| Eight teachers submitting eight different sessions simultaneously | All 8 returned HTTP 302; 30 records saved per session |

### Observations

- No duplicate attendance records were created.
- Simultaneous submissions completed successfully.
- Alert creation produced one alert per absent student.
- The database uniqueness constraint and transactional submission handling prevented duplicate records.

## 5. Attendance Report Testing

A total of 18 report tests passed.

The tests covered:

- CSV export contents and correctness.
- Date filtering.
- Access permissions.
- Formula-injection sanitization.
- Report form validation.
- Handling of reports with no attendance records.

### Observations

Generated report contents and export behavior passed the automated checks. Permission restrictions and input sanitization were also verified.

## 6. Usability Evaluation

Manual browser-based usability testing was not performed.

The automated tests verified important workflow behavior, response handling and access restrictions. However, visual clarity, navigation convenience and ease of use were not evaluated through manual interaction.

This remains a limitation of the evaluation.

## 7. Defects Identified and Resolved

| # | Defect | Severity | Status |
|---|---|---|---|
| 1 | Concurrent submissions failed with `database is locked` under default SQLite settings. | High | Fixed using SQLite timeout of 30 seconds and `transaction_mode: IMMEDIATE` in `sams/settings.py`. Retested successfully. |
| 2 | Repeating a successful attendance submission displayed the message "No attendance data was submitted". | Low (UX) | Fixed in `attendance_views.py` by displaying an informational message when all records already exist. Retested successfully. |

No failures were observed in the final automated test run.

## 8. Full Automated Test Results

Commands executed:

```powershell
python manage.py check
python manage.py test attendance -v 2
```

Results:

- Django system check: No issues identified.
- Total automated tests: 335.
- Tests passed: 335.
- Tests failed: 0.
- Total execution time: 196.312 seconds.

The full test suite included attendance workflows, permissions, security, concurrency, performance and report tests.

## 9. Limitations

- Manual UI usability testing was not performed.
- Performance measurements were obtained using the Django test client on one machine; network latency and real browser behavior were not measured.
- Results are based on SQLite. Concurrency behavior should be tested again if the application moves to MySQL or PostgreSQL.
- SQLite permits only one writer at a time, which may limit scalability under heavier concurrent workloads.
- Performance measurements are local test observations, not production load-test results.

## 10. Conclusion

The automated evaluation of SAMS was successful. All 335 automated tests passed, including performance, concurrency and report-generation tests.

Attendance submissions worked correctly for class sizes up to 200 students in the tested environment. Concurrent submissions did not produce duplicate records, and report export and validation checks passed.

The previously identified concurrency and repeat-submission issues were resolved and retested.

Manual UI usability evaluation remains outstanding and should be performed in a future testing cycle.
