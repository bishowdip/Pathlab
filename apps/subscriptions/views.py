import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .gateways import verify_esewa_signature, verify_khalti_payment
from .models import Coupon, Payment, Plan, Subscription
from .services import send_payment_receipt


def _confirm_payment(payment, *, note):
    """
    Shared guard for all gateway success callbacks.

    Returns (ok, message). Refuses if:
    - payment already settled (idempotency — no double-activation)
    - sandbox mode is off (real gateway verification must happen in caller first)
    """
    if payment.status == "success":
        return False, "This payment is already confirmed."
    if payment.status != "initiated":
        return False, "This payment cannot be confirmed in its current state."
    if not settings.PAYMENT_SANDBOX:
        # Prod code paths must verify with the gateway BEFORE calling this helper
        # and flip payment.status themselves. The stub callback refuses to act.
        return False, "Stub confirmation disabled in production."
    payment.status = "success"
    payment.raw_response = {"stub": True, "note": note}
    payment.save(update_fields=["status", "raw_response"])
    payment.subscription.activate()
    # Best-effort — never let email failure block activation.
    try:
        send_payment_receipt(payment)
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("Receipt email failed for %s", payment.pk)
    return True, "Payment successful. Your plan is active!"


def _confirm_payment_verified(payment, *, raw):
    """Like _confirm_payment, but caller already verified with the gateway —
    so we bypass the PAYMENT_SANDBOX guard. Still idempotent."""
    if payment.status == "success":
        return False, "This payment is already confirmed."
    if payment.status != "initiated":
        return False, "This payment cannot be confirmed in its current state."
    payment.status = "success"
    payment.raw_response = raw
    payment.save(update_fields=["status", "raw_response"])
    payment.subscription.activate()
    try:
        send_payment_receipt(payment)
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("Receipt email failed for %s", payment.pk)
    return True, "Payment successful. Your plan is active!"


@login_required
def my_subscription(request):
    """Customer self-service: see current plan, history, download receipts."""
    subs = (Subscription.objects
            .filter(user=request.user)
            .select_related("plan", "coupon")
            .prefetch_related("payments"))
    current = subs.filter(status="active").first()
    # Proactively expire stale ones so the UI shows the truth.
    if current and not current.is_active():
        current = None
    return render(request, "subscriptions/my_subscription.html",
                  {"current": current, "subscriptions": subs})


@login_required
@require_POST
def cancel_subscription(request, pk):
    """
    Soft-cancel: user keeps access until expires_at, but auto-renew won't happen
    (we don't renew automatically today — this just flips status for clarity).
    """
    sub = get_object_or_404(Subscription, pk=pk, user=request.user)
    if sub.status != "active":
        messages.error(request, "Only active subscriptions can be cancelled.")
        return redirect("subscriptions:my_subscription")
    sub.status = "cancelled"
    sub.save(update_fields=["status"])
    messages.success(
        request,
        "Subscription cancelled. You still have access until "
        f"{sub.expires_at:%b %d, %Y}." if sub.expires_at else "Subscription cancelled."
    )
    return redirect("subscriptions:my_subscription")


@login_required
def receipt(request, payment_id):
    """Printable receipt for a single successful payment."""
    payment = get_object_or_404(
        Payment, id=payment_id, subscription__user=request.user, status="success"
    )
    return render(request, "subscriptions/receipt.html", {"payment": payment})


def pricing(request):
    plans = Plan.objects.filter(is_active=True)
    return render(request, "subscriptions/pricing.html", {"plans": plans})


@login_required
def checkout(request, slug):
    plan = get_object_or_404(Plan, slug=slug, is_active=True)

    # Coupon can come in via GET (applied) or POST (submitted with gateway).
    code = (request.GET.get("code") or request.POST.get("code") or "").strip().upper()
    coupon = None
    final_price = plan.price_npr
    coupon_error = None
    if code:
        coupon = Coupon.objects.filter(code__iexact=code).first()
        if not coupon or not coupon.is_valid(plan=plan):
            coupon_error = "That coupon is invalid or expired."
            coupon = None
        else:
            final_price = coupon.apply(plan.price_npr)

    if request.method == "POST":
        # "Apply coupon" button — don't create a subscription yet.
        if request.POST.get("action") == "apply_coupon":
            if coupon_error:
                messages.error(request, coupon_error)
            elif coupon:
                messages.success(request, f"Coupon applied: {coupon.percent_off}% off.")
            return render(request, "subscriptions/checkout.html",
                          {"plan": plan, "coupon": coupon, "final_price": final_price,
                           "coupon_error": coupon_error})

        gateway = request.POST.get("gateway")
        if gateway not in {"esewa", "khalti", "stripe", "paypal"}:
            return HttpResponseBadRequest("Unknown gateway")

        subscription = Subscription.objects.create(
            user=request.user, plan=plan, status="pending",
            coupon=coupon,
            discounted_price=final_price if coupon else None,
        )
        if coupon:
            # Atomic increment — prevents races when two buyers redeem the last
            # slot of a limited coupon at the same time.
            Coupon.objects.filter(pk=coupon.pk).update(
                times_redeemed=F("times_redeemed") + 1
            )
        payment = Payment.objects.create(
            subscription=subscription,
            gateway=gateway,
            amount=final_price,
            currency="NPR",
            reference=f"TXN-{uuid.uuid4().hex[:10].upper()}",
            status="initiated",
        )

        if gateway == "esewa":
            return redirect("subscriptions:esewa_init", payment_id=payment.id)
        if gateway == "khalti":
            return redirect("subscriptions:khalti_init", payment_id=payment.id)
        if gateway == "stripe":
            return redirect("subscriptions:stripe_init", payment_id=payment.id)
        if gateway == "paypal":
            return redirect("subscriptions:paypal_init", payment_id=payment.id)

    return render(request, "subscriptions/checkout.html",
                  {"plan": plan, "coupon": coupon, "final_price": final_price,
                   "coupon_error": coupon_error})


# --- PayPal stub --------------------------------------------------------
@login_required
def paypal_init(request, payment_id):
    payment = get_object_or_404(
        Payment, id=payment_id, subscription__user=request.user, gateway="paypal"
    )
    return render(request, "subscriptions/paypal_redirect.html", {"payment": payment})


@login_required
def paypal_success(request, payment_id):
    payment = get_object_or_404(
        Payment, id=payment_id, subscription__user=request.user, gateway="paypal"
    )
    ok, msg = _confirm_payment(payment, note="PayPal sandbox stub")
    (messages.success if ok else messages.error)(request, msg)
    return redirect("accounts:dashboard" if ok else "subscriptions:pricing")


# --- eSewa stub ---------------------------------------------------------
@login_required
def esewa_init(request, payment_id):
    """Stub: in prod, POST to eSewa's endpoint. Here we just render a confirm page."""
    payment = get_object_or_404(
        Payment, id=payment_id, subscription__user=request.user, gateway="esewa"
    )
    gateway_config = settings.PAYMENT_GATEWAYS["esewa"]
    return render(
        request,
        "subscriptions/esewa_redirect.html",
        {"payment": payment, "gateway_config": gateway_config},
    )


@login_required
def esewa_success(request):
    """
    eSewa v2 posts back `total_amount`, `transaction_uuid`, `product_code`,
    `signed_field_names`, `signature`. Verify HMAC server-side before trusting.

    Back-compat: if only `?ref=` is present (our old sandbox shape) and
    PAYMENT_SANDBOX is on, we still allow stub confirmation via _confirm_payment.
    """
    data = request.POST if request.method == "POST" else request.GET
    signature = data.get("signature")
    txn_uuid = data.get("transaction_uuid")
    ref = data.get("ref")

    # Real v2 callback path — HMAC-verified, works even in production.
    if signature and txn_uuid:
        payment = Payment.objects.filter(reference=txn_uuid, gateway="esewa").first()
        if not payment:
            messages.error(request, "Payment not found.")
            return redirect("subscriptions:pricing")
        payload = {
            "total_amount": data.get("total_amount", ""),
            "transaction_uuid": txn_uuid,
            "product_code": data.get("product_code", ""),
        }
        if not verify_esewa_signature(payload, signature):
            messages.error(request, "Payment signature invalid — refusing to activate.")
            return redirect("subscriptions:pricing")
        ok, msg = _confirm_payment_verified(payment, raw={"verified": True, **payload})
        (messages.success if ok else messages.error)(request, msg)
        return redirect("accounts:dashboard" if ok else "subscriptions:pricing")

    # Legacy/sandbox path — only honoured when PAYMENT_SANDBOX is on.
    payment = Payment.objects.filter(reference=ref, gateway="esewa").first()
    if not payment:
        messages.error(request, "Payment not found.")
        return redirect("subscriptions:pricing")
    ok, msg = _confirm_payment(payment, note="eSewa sandbox — replace with real verify call")
    (messages.success if ok else messages.error)(request, msg)
    return redirect("accounts:dashboard" if ok else "subscriptions:pricing")


@login_required
def esewa_failure(request):
    messages.error(request, "eSewa payment failed or was cancelled.")
    return redirect("subscriptions:pricing")


# --- Khalti stub --------------------------------------------------------
@login_required
def khalti_init(request, payment_id):
    payment = get_object_or_404(
        Payment, id=payment_id, subscription__user=request.user, gateway="khalti"
    )
    gateway_config = settings.PAYMENT_GATEWAYS["khalti"]
    return render(
        request,
        "subscriptions/khalti_redirect.html",
        {"payment": payment, "gateway_config": gateway_config},
    )


@login_required
def khalti_verify(request, payment_id):
    """
    Khalti ePayment v2 callback. Khalti redirects the user back with a `pidx`
    (along with `status`, `transaction_id`, `amount`). We ignore their
    client-side status and call `/epayment/lookup/` with our merchant secret
    — that's the only trustworthy confirmation.

    Falls back to a sandbox stub only when PAYMENT_SANDBOX=1 and no pidx is
    present, so local "click through" flows keep working in dev.
    """
    payment = get_object_or_404(
        Payment, id=payment_id, subscription__user=request.user, gateway="khalti"
    )
    pidx = request.GET.get("pidx") or request.POST.get("pidx")

    if pidx:
        verified = verify_khalti_payment(pidx)
        if not verified:
            messages.error(request, "Khalti could not confirm this payment — refusing to activate.")
            return redirect("subscriptions:pricing")
        ok, msg = _confirm_payment_verified(payment, raw={"pidx": pidx, **verified})
        (messages.success if ok else messages.error)(request, msg)
        return redirect("accounts:dashboard" if ok else "subscriptions:pricing")

    # No pidx — legacy/sandbox stub path. Only honoured when PAYMENT_SANDBOX=1.
    ok, msg = _confirm_payment(payment, note="Khalti sandbox stub")
    (messages.success if ok else messages.error)(request, msg)
    return redirect("accounts:dashboard" if ok else "subscriptions:pricing")


# --- Stripe stub --------------------------------------------------------
@login_required
def stripe_init(request, payment_id):
    payment = get_object_or_404(
        Payment, id=payment_id, subscription__user=request.user, gateway="stripe"
    )
    return render(
        request,
        "subscriptions/stripe_redirect.html",
        {"payment": payment},
    )


@login_required
def stripe_success(request, payment_id):
    payment = get_object_or_404(
        Payment, id=payment_id, subscription__user=request.user, gateway="stripe"
    )
    ok, msg = _confirm_payment(payment, note="Stripe sandbox stub")
    (messages.success if ok else messages.error)(request, msg)
    return redirect("accounts:dashboard" if ok else "subscriptions:pricing")
