"""
Gateway verification helpers — keep crypto and HTTP calls out of views.

- eSewa v2: HMAC-SHA256 signature computed locally, constant-time compared.
- Khalti ePayment v2: server-side lookup by `pidx` against Khalti's
  `/epayment/lookup/` endpoint using the merchant secret.

Stripe/PayPal still go through the sandbox stub — wire up equivalents here
when those gateways go live.
"""
import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


# eSewa v2 canonical signed fields (order matters — gateway docs are explicit).
ESEWA_SIGNED_FIELDS = ("total_amount", "transaction_uuid", "product_code")


def esewa_signature(data: dict, secret: str | None = None) -> str:
    """
    Build the base64(HMAC-SHA256) signature eSewa v2 expects.

    eSewa signs a comma-separated `key=value,key=value,...` string using the
    `signed_field_names` order and the merchant secret. Sandbox secret is
    `8gBm/:&EnhH.1/q` per eSewa v2 docs — only used when PAYMENT_SANDBOX=1.
    """
    if secret is None:
        secret = settings.PAYMENT_GATEWAYS["esewa"].get("secret_key") or ""
        if not secret:
            if not getattr(settings, "PAYMENT_SANDBOX", False):
                raise ImproperlyConfigured(
                    "ESEWA_SECRET_KEY is required when PAYMENT_SANDBOX is off."
                )
            # Documented eSewa sandbox secret — safe to use only in dev.
            secret = "8gBm/:&EnhH.1/q"
    message = ",".join(f"{k}={data[k]}" for k in ESEWA_SIGNED_FIELDS)
    digest = hmac.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def verify_esewa_signature(data: dict, received_signature: str) -> bool:
    """Constant-time compare against the signature we recompute locally."""
    if not received_signature:
        return False
    try:
        expected = esewa_signature(data)
    except KeyError:
        return False
    return hmac.compare_digest(expected, received_signature)


# ---------------- Khalti ePayment v2 ----------------

# Live and sandbox endpoints per Khalti docs.
KHALTI_LOOKUP_URL_LIVE = "https://khalti.com/api/v2/epayment/lookup/"
KHALTI_LOOKUP_URL_SANDBOX = "https://a.khalti.com/api/v2/epayment/lookup/"


def _khalti_secret() -> str:
    secret = settings.PAYMENT_GATEWAYS["khalti"].get("secret_key") or ""
    if not secret or secret == "test_secret_key_stub":
        if not getattr(settings, "PAYMENT_SANDBOX", False):
            raise ImproperlyConfigured(
                "KHALTI_SECRET_KEY is required when PAYMENT_SANDBOX is off."
            )
    return secret


def verify_khalti_payment(pidx: str) -> dict | None:
    """
    Call Khalti's lookup endpoint to verify the payment identified by `pidx`.

    Returns the parsed JSON on a `Completed` status, or None if the call
    fails, the status isn't Completed, or the response can't be parsed.
    Keeping the failure mode binary (dict | None) makes the caller simple:
    a truthy result means "trust this payment and activate".
    """
    if not pidx:
        return None
    secret = _khalti_secret()
    url = (KHALTI_LOOKUP_URL_SANDBOX
           if getattr(settings, "PAYMENT_SANDBOX", False)
           else KHALTI_LOOKUP_URL_LIVE)
    body = json.dumps({"pidx": pidx}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Authorization": f"Key {secret}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, TimeoutError):
        return None
    if payload.get("status") != "Completed":
        return None
    return payload
