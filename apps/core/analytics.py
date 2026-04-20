"""Read-only aggregates for the staff analytics dashboard."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.utils import timezone

from apps.courses.models import Course, Enrollment
from apps.exams.models import Exam
from apps.subscriptions.models import Payment, Subscription
from apps.support.models import SupportThread


def _range(days):
    now = timezone.now()
    return now - timedelta(days=days), now


def collect():
    User = get_user_model()
    now = timezone.now()
    thirty_days_ago, _ = _range(30)
    seven_days_ago, _ = _range(7)

    total_users = User.objects.count()
    new_users_30d = User.objects.filter(date_joined__gte=thirty_days_ago).count()
    new_users_7d = User.objects.filter(date_joined__gte=seven_days_ago).count()

    total_enrollments = Enrollment.objects.count()
    new_enrollments_30d = Enrollment.objects.filter(started_at__gte=thirty_days_ago).count()
    completions_30d = Enrollment.objects.filter(completed_at__gte=thirty_days_ago).count()

    active_subs = Subscription.objects.filter(status="active").count()
    revenue_total = Payment.objects.filter(status="success").aggregate(
        s=Sum("amount"))["s"] or 0
    revenue_30d = Payment.objects.filter(
        status="success", created_at__gte=thirty_days_ago,
    ).aggregate(s=Sum("amount"))["s"] or 0

    top_courses = (
        Course.objects.filter(published=True)
        .annotate(enroll_count=Count("enrollments"))
        .order_by("-enroll_count")[:5]
    )

    pending_support = SupportThread.objects.filter(
        status__in=["awaiting_agent", "with_agent"]
    ).count()

    payments_recent = (
        Payment.objects.select_related("subscription__user", "subscription__plan")
        .order_by("-created_at")[:10]
    )

    return {
        "total_users": total_users,
        "new_users_30d": new_users_30d,
        "new_users_7d": new_users_7d,
        "total_enrollments": total_enrollments,
        "new_enrollments_30d": new_enrollments_30d,
        "completions_30d": completions_30d,
        "active_subs": active_subs,
        "revenue_total": revenue_total,
        "revenue_30d": revenue_30d,
        "top_courses": top_courses,
        "pending_support": pending_support,
        "payments_recent": payments_recent,
        "course_count": Course.objects.filter(published=True).count(),
        "exam_count": Exam.objects.filter(published=True).count(),
        "generated_at": now,
    }
