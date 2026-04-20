from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import LoginView, LogoutView
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str
from django.utils.http import (
    url_has_allowed_host_and_scheme, urlsafe_base64_decode, urlsafe_base64_encode,
)

from apps.core.ratelimit import rate_limit

from .forms import ProfileForm, SignupForm
from .models import NewsletterSubscription, Profile

User = get_user_model()


def _send_verification_email(request, user):
    if not user.email:
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("accounts:verify_email", kwargs={"uidb64": uid, "token": token})
    # Prefer the configured SITE_URL so a Host-header-spoofed request can't
    # point the verification link at an attacker domain. build_absolute_uri
    # is only used as a dev convenience when SITE_URL isn't set.
    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
    link = f"{site_url}{path}" if site_url else request.build_absolute_uri(path)
    send_mail(
        "Confirm your PathLab email",
        (
            f"Hi {user.username},\n\n"
            f"Please confirm your email to finish creating your account:\n\n{link}\n\n"
            "If you didn't sign up, you can ignore this message.\n"
        ),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def _get_profile(user):
    """Return the user's Profile, creating one on the fly for legacy accounts."""
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


class AppLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class AppLogoutView(LogoutView):
    next_page = reverse_lazy("core:home")


def signup(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # gated until email confirmed
            user.save()
            form.save_m2m() if hasattr(form, "save_m2m") else None
            _get_profile(user)  # trigger profile creation
            try:
                _send_verification_email(request, user)
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).exception("Verification email failed for %s", user.pk)
            return redirect("accounts:signup_pending")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})


def signup_pending(request):
    return render(request, "accounts/signup_pending.html")


def verify_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user and default_token_generator.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        login(request, user)
        messages.success(request, "Email confirmed — welcome aboard.")
        if _get_profile(user).role == "kid":
            return redirect("accounts:kids_dashboard")
        return redirect("accounts:dashboard")
    return render(request, "accounts/verify_email_invalid.html", status=400)


@rate_limit(key="resend_verify", max_hits=3, window_seconds=600)
def resend_verification(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        user = User.objects.filter(email__iexact=email, is_active=False).first()
        if user:
            try:
                _send_verification_email(request, user)
            except Exception:  # noqa: BLE001
                pass
        # Always the same response — don't leak which emails are registered.
        messages.success(request, "If that email is pending verification, we've sent a new link.")
        return redirect("accounts:login")
    return render(request, "accounts/resend_verification.html")


@login_required
def dashboard(request):
    profile = _get_profile(request.user)
    if profile.role == "kid":
        return redirect("accounts:kids_dashboard")
    attempts = request.user.attempts.select_related("exam")[:10]
    subscriptions = request.user.subscriptions.select_related("plan")
    enrollments = request.user.enrollments.select_related("course", "course__category")
    return render(
        request,
        "accounts/dashboard.html",
        {"attempts": attempts, "subscriptions": subscriptions, "enrollments": enrollments},
    )


@login_required
def kids_dashboard(request):
    """Simplified big-button UI for kids with badges + progress bars."""
    enrollments = (
        request.user.enrollments
        .filter(course__category__pillar="kids")
        .select_related("course", "course__category")
    )
    badges = request.user.badges.select_related("badge")
    return render(
        request,
        "accounts/kids_dashboard.html",
        {"enrollments": enrollments, "badges": badges},
    )


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=_get_profile(request.user))
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=_get_profile(request.user))
    return render(request, "accounts/profile.html", {"form": form})


@rate_limit(key="newsletter", max_hits=5, window_seconds=300)
def newsletter_signup(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        source = request.POST.get("source", "footer")
        if email:
            NewsletterSubscription.objects.get_or_create(
                email=email, defaults={"source": source}
            )
            messages.success(request, "Thanks — you're on the list.")
    # Open-redirect guard: Referer is attacker-controlled, so bounce only to
    # same-origin URLs. Anything off-site falls back to home.
    ref = request.META.get("HTTP_REFERER") or ""
    if ref and url_has_allowed_host_and_scheme(
        url=ref, allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(ref)
    return redirect("core:home")
