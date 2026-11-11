from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from .attendance_services import (
    get_markable_session,
    get_session_students,
    submit_attendance,
)
from .models import AttendanceRecord


@login_required
def mark_attendance(request, session_id):
    session = get_markable_session(request.user, session_id)

    enrollments = list(get_session_students(session))

    existing_records = {
        record.student_id: record
        for record in AttendanceRecord.objects.filter(session=session)
    }

    student_rows = [
        {
            "student": enrollment.student,
            "record": existing_records.get(enrollment.student_id),
        }
        for enrollment in enrollments
    ]

    if request.method == "POST":
        attendance_data = {}

        for row in student_rows:
            student = row["student"]

            if row["record"] is None:
                status = request.POST.get(f"status_{student.id}")

                if status:
                    attendance_data[student.id] = status

        try:
            result = submit_attendance(
                request.user,
                session_id,
                attendance_data,
            )

            messages.success(
                request,
                (
                    f"Attendance saved: {result['created']} new records. "
                    f"{result['skipped']} existing records were left unchanged."
                ),
            )

            return redirect(
                "attendance:mark_attendance",
                session_id=session_id,
            )

        except ValidationError as error:
            messages.error(request, str(error))

    return render(
        request,
        "attendance/mark_attendance.html",
        {
            "session": session,
            "student_rows": student_rows,
        },
    )