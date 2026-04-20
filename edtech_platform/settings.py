from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# DEBUG is OFF by default — must be opt-in via env. This flips the default
# from "insecure unless you set DJANGO_DEBUG=0" to "secure unless you set =1".
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

_SECRET_KEY_DEV_FALLBACK = "django-insecure-f1x1k9ylif4ot4ezvfy%mgs-*tdaq)x3o6!2x%)0h%agj)%7fl"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or (
    _SECRET_KEY_DEV_FALLBACK if DEBUG else None
)
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set when DEBUG is off."
    )

if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = [h.strip() for h in
                     os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
                     if h.strip()]
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must be set when DEBUG is off."
        )

CSRF_TRUSTED_ORIGINS = [o.strip() for o in
                        os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
                        if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "apps.accounts",
    "apps.core",
    "apps.courses",
    "apps.exams",
    "apps.subscriptions",
    "apps.support",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.subscriptions.middleware.SubscriptionAccessMiddleware",
]

ROOT_URLCONF = "edtech_platform.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "edtech_platform.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kathmandu"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"

# Dev: print emails (incl. password-reset) to console.
# Prod: switch to django.core.mail.backends.smtp.EmailBackend + SMTP creds.
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_FROM_EMAIL", "PathLab <no-reply@pathlab.local>")

# When True, gateway success callbacks accept stub confirmations (no real verify
# call). MUST be False in production — otherwise anyone can forge a success URL.
PAYMENT_SANDBOX = os.environ.get("PAYMENT_SANDBOX", "1" if DEBUG else "0") == "1"

PAYMENT_GATEWAYS = {
    "esewa": {
        "merchant_id": os.environ.get("ESEWA_MERCHANT_ID", "EPAYTEST"),
        "secret_key": os.environ.get("ESEWA_SECRET_KEY", ""),
        "success_url": "/subscriptions/payment/esewa/success/",
        "failure_url": "/subscriptions/payment/esewa/failure/",
        "sandbox": True,
    },
    "khalti": {
        "public_key": os.environ.get("KHALTI_PUBLIC_KEY", "test_public_key_stub"),
        "secret_key": os.environ.get("KHALTI_SECRET_KEY", "test_secret_key_stub"),
        "sandbox": True,
    },
    "stripe": {
        "public_key": os.environ.get("STRIPE_PUBLIC_KEY", "pk_test_stub"),
        "secret_key": os.environ.get("STRIPE_SECRET_KEY", "sk_test_stub"),
    },
}

# Absolute site URL — used by email-sent links (verification, password reset)
# so Host-header spoofing on build_absolute_uri can't redirect tokens to an
# attacker domain. Required in production.
SITE_URL = os.environ.get("DJANGO_SITE_URL", "").rstrip("/")
if not DEBUG and not SITE_URL:
    raise ImproperlyConfigured(
        "DJANGO_SITE_URL must be set when DEBUG is off."
    )

# Production hardening. Keep dev untouched so runserver still works.
if not DEBUG:
    if EMAIL_BACKEND.endswith(".console.EmailBackend"):
        raise ImproperlyConfigured(
            "Console email backend in production — set DJANGO_EMAIL_BACKEND."
        )
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days; ramp to 1y after verifying
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    # Trust the X-Forwarded-Proto header from the reverse proxy.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Reverse-proxy config for the rate limiter (see apps.core.ratelimit).
# When behind Cloudflare/Nginx, set this to the number of proxies sitting in
# front of the app so HTTP_X_FORWARDED_FOR is parsed safely.
TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))
