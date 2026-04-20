from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from apps.core.ratelimit import rate_limit

from . import views

# Throttle sensitive auth endpoints — 10 hits per 10 min per IP bucket.
_AUTH_RL = dict(max_hits=10, window_seconds=600)

urlpatterns = [
    path("login/",
         rate_limit(key="login", **_AUTH_RL)(views.AppLoginView.as_view()),
         name="login"),
    path("logout/", views.AppLogoutView.as_view(), name="logout"),
    path("signup/", rate_limit(key="signup", **_AUTH_RL)(views.signup), name="signup"),
    path("signup/pending/", views.signup_pending, name="signup_pending"),
    path("verify/<uidb64>/<token>/", views.verify_email, name="verify_email"),
    path("verify/resend/", views.resend_verification, name="resend_verification"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("kids/", views.kids_dashboard, name="kids_dashboard"),
    path("profile/", views.profile, name="profile"),
    path("newsletter/", views.newsletter_signup, name="newsletter"),

    # password reset
    path(
        "password/reset/",
        rate_limit(key="pw_reset", max_hits=5, window_seconds=600)(
            auth_views.PasswordResetView.as_view(
                template_name="accounts/password_reset.html",
                email_template_name="accounts/password_reset_email.txt",
                success_url=reverse_lazy("accounts:password_reset_done"),
            )
        ),
        name="password_reset",
    ),
    path(
        "password/reset/sent/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "password/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
