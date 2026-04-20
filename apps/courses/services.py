"""Side-effects that aren't core to a view — email, notifications, etc."""
from django.conf import settings
from django.core.mail import send_mail


def notify_enrollment(enrollment):
    """Fire-and-forget welcome email. Swallows errors so it never breaks the view."""
    user = enrollment.user
    if not user.email:
        return
    course = enrollment.course
    try:
        send_mail(
            subject=f"Welcome to {course.title}",
            message=(
                f"Hi {user.get_full_name() or user.username},\n\n"
                f"You've just enrolled in {course.title}. "
                f"Your first lesson is waiting — jump in whenever you're ready.\n\n"
                f"— PathLab"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception:
        pass


def _instructor_email(course):
    """Best-effort lookup of the email address to notify for a course."""
    instr = getattr(course, "instructor", None)
    user = getattr(instr, "user", None)
    return getattr(user, "email", "") or ""


def notify_course_review_decision(course, decision, notes=""):
    """Email the course owner when staff approves or requests changes."""
    to = _instructor_email(course)
    if not to:
        return
    if decision == "approved":
        subject = f"“{course.title}” is approved and live"
        body = (
            f"Good news — your course “{course.title}” was approved and is now published.\n\n"
            f"Students can find it at: /courses/{course.slug}/\n\n"
            f"— PathLab"
        )
    elif decision == "changes_requested":
        subject = f"Changes requested on “{course.title}”"
        body = (
            f"Thanks for submitting “{course.title}” for review. "
            f"A staff member has asked for a few changes before it can go live:\n\n"
            f"{notes or 'Please revise and resubmit.'}\n\n"
            f"Once you've addressed the feedback, hit Publish again to resubmit.\n\n"
            f"— PathLab"
        )
    else:
        return
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=True)
    except Exception:
        pass


def notify_course_completion(enrollment):
    user = enrollment.user
    if not user.email:
        return
    course = enrollment.course
    try:
        send_mail(
            subject=f"🎉 You finished {course.title}!",
            message=(
                f"Hi {user.get_full_name() or user.username},\n\n"
                f"Huge — you just completed every lesson in {course.title}. "
                f"Your certificate is live on your dashboard.\n\n"
                f"— PathLab"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception:
        pass
