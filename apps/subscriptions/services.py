"""Side-effectful subscription helpers — email, revenue hooks, etc."""
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse


def send_payment_receipt(payment):
    """Email the user a receipt. fail_silently=False so tests can see it
    in locmem; callers wrap this in try/except so it never blocks activation."""
    user = payment.subscription.user
    if not user.email:
        return
    plan = payment.subscription.plan
    try:
        receipt_path = reverse("subscriptions:receipt", kwargs={"payment_id": payment.id})
    except Exception:  # noqa: BLE001
        receipt_path = ""
    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
    receipt_url = f"{site_url}{receipt_path}" if site_url and receipt_path else receipt_path

    subject = f"Your PathLab receipt — {plan.name}"
    lines = [
        f"Hi {user.get_full_name() or user.username},",
        "",
        f"Thanks for subscribing to {plan.name}. Your payment was successful.",
        "",
        f"  Reference: {payment.reference}",
        f"  Gateway:   {payment.get_gateway_display()}",
        f"  Amount:    {payment.currency} {payment.amount}",
        f"  Date:      {payment.created_at:%b %d, %Y %H:%M}",
        "",
    ]
    if receipt_url:
        lines += [f"View or print your receipt: {receipt_url}", ""]
    lines += ["— The PathLab team"]
    send_mail(
        subject,
        "\n".join(lines),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def refund_payment(payment, *, reason=""):
    """
    Mark a payment refunded and expire its subscription. Idempotent.
    Real gateway refund API calls go here too — today it's bookkeeping only.
    """
    if payment.status == "refunded":
        return False
    if payment.status != "success":
        raise ValueError("Only successful payments can be refunded.")
    payment.status = "refunded"
    existing = payment.raw_response or {}
    existing["refund"] = {"reason": reason or "admin-refund"}
    payment.raw_response = existing
    payment.save(update_fields=["status", "raw_response"])

    sub = payment.subscription
    if sub.status == "active":
        sub.status = "expired"
        sub.save(update_fields=["status"])
    return True
