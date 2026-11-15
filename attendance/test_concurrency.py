import threading

from django.db import connection
from django.test import Client, TransactionTestCase
from django.urls import reverse

from .models import AttendanceAlert, AttendanceRecord
from .test_performance import build_class


def run_parallel(jobs):
    """jobs = list of (client, url, data). Fires all POSTs at the same moment."""
    barrier = threading.Barrier(len(jobs))
    results = [None] * len(jobs)

    def worker(i, client, url, data):
        try:
            barrier.wait()
            results[i] = client.post(url, data).status_code
        except Exception as exc:
            results[i] = f"ERR {type(exc).__name__}: {exc}"
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(i, *job))
        for i, job in enumerate(jobs)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


class ConcurrentSubmissionTests(TransactionTestCase):

    def make_job(self, teacher, session, students):
        client = Client()
        client.force_login(teacher)
        url = reverse(
            "attendance:mark_attendance", kwargs={"session_id": session.id}
        )
        data = {f"status_{s.id}": "PRESENT" for s in students}
        return client, url, data

    def test_same_session_submitted_5_times_at_once(self):
        teacher, session, students = build_class(30, "dup")
        jobs = [self.make_job(teacher, session, students) for _ in range(5)]

        results = run_parallel(jobs)

        rows = AttendanceRecord.objects.filter(session=session).count()
        print(f"\n[same session x5] responses: {results} | rows: {rows}/30 "
              f"| alerts: {AttendanceAlert.objects.count()}")
        self.assertEqual(rows, 30)

    def test_8_teachers_different_sessions_at_once(self):
        classes = [build_class(30, f"c{i}") for i in range(8)]
        jobs = [self.make_job(t, s, st) for t, s, st in classes]

        results = run_parallel(jobs)

        counts = [
            AttendanceRecord.objects.filter(session=s).count()
            for _, s, _ in classes
        ]
        print(f"\n[8 teachers] responses: {results} | rows per session: {counts}")
        self.assertEqual(counts, [30] * 8)


class ConcurrentAlertTests(TransactionTestCase):

    def test_same_session_absent_x5_alerts(self):
        teacher, session, students = build_class(30, "alert")
        client_jobs = []
        for _ in range(5):
            client = Client()
            client.force_login(teacher)
            url = reverse(
                "attendance:mark_attendance", kwargs={"session_id": session.id}
            )
            data = {f"status_{s.id}": "ABSENT" for s in students}
            client_jobs.append((client, url, data))

        results = run_parallel(client_jobs)

        rows = AttendanceRecord.objects.filter(session=session).count()
        alerts = AttendanceAlert.objects.count()
        print(f"\n[absent x5] responses: {results} | rows: {rows}/30 | alerts: {alerts}")
        self.assertEqual(rows, 30)
        self.assertTrue(all(r == 302 or r == 200 for r in results))
