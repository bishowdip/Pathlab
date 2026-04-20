import re

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


PRO_PATH_PREFIXES = ("/exams/take/",)
_TAKE_ATTEMPT_RE = re.compile(r"^/exams/take/(?P<id>\d+)/")


class SubscriptionAccessMiddleware(MiddlewareMixin):
    """
    Protect 'Pro' content: exam-taking URLs require an active subscription.
    This is a coarse backstop — view-level checks are the source of truth.
    Free-preview exams (and the plan-scoped exams the view gates explicitly)
    are allowed through so the view can apply the fine-grained rules.
    """

    def process_request(self, request):
        path = request.path
        if not any(path.startswith(p) for p in PRO_PATH_PREFIXES):
            return None
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={path}")
        if request.user.is_staff:
            return None

        # If the underlying exam is a free preview, let the view decide.
        m = _TAKE_ATTEMPT_RE.match(path)
        if m:
            from apps.exams.models import ExamAttempt
            attempt = (ExamAttempt.objects
                       .select_related("exam")
                       .filter(id=m.group("id"), user=request.user)
                       .first())
            if attempt and (attempt.exam.is_free_preview
                            or not attempt.exam.requires_subscription):
                return None

        has_active = request.user.subscriptions.filter(status="active").exists()
        if not has_active:
            return redirect(reverse("subscriptions:pricing"))
        return None
