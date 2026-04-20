"""
Cross-app smoke tests. Run with:
    .venv/bin/python manage.py test apps.tests_smoke

Covers: public pages load, auth flow, course enrollment + gating,
coupon application, lesson notes, review posting, certificate gating,
support chat, rate limiting, staff dashboard access control.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Profile
from apps.courses.models import (
    Category, Course, CourseReview, Enrollment, Instructor,
    Lesson, LessonNote, Module,
)
from django.core import mail

from apps.subscriptions.gateways import esewa_signature, verify_esewa_signature
from apps.subscriptions.models import Coupon, Payment, Plan, Subscription
from apps.subscriptions.services import refund_payment, send_payment_receipt
from apps.exams.models import Choice, Exam, ExamAttempt, Question
from apps.support.models import SupportThread


User = get_user_model()


def make_course(*, is_free=False, price=Decimal("500.00")):
    cat, _ = Category.objects.get_or_create(
        slug="entrance-test", defaults={"name": "Entrance Test", "pillar": "entrance"},
    )
    course = Course.objects.create(
        category=cat, title="Test Course", slug="test-course",
        description="demo", price_npr=price, is_free=is_free, published=True,
    )
    module = Module.objects.create(course=course, title="M1", order=1)
    lesson = Lesson.objects.create(
        module=module, title="L1", slug="l1", kind="article",
        body="content", order=1,
    )
    return course, module, lesson


# ---------------- Public pages ----------------

class PublicPagesTests(TestCase):
    def test_home(self):
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)

    def test_about_contact_terms_privacy_instructors(self):
        for name in ["core:about", "core:contact", "core:terms",
                     "core:privacy", "core:instructors"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_robots_and_sitemap(self):
        self.assertEqual(self.client.get("/robots.txt").status_code, 200)
        self.assertEqual(self.client.get("/sitemap.xml").status_code, 200)

    def test_custom_404(self):
        self.assertEqual(self.client.get("/definitely-missing/").status_code, 404)


# ---------------- Auth ----------------

class AuthFlowTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_signup_requires_email_verification(self):
        mail.outbox = []
        r = self.client.post(reverse("accounts:signup"), {
            "username": "alice", "email": "a@x.com", "role": "student",
            "country": "Nepal",
            "password1": "hunter22test!", "password2": "hunter22test!",
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn("/signup/pending/", r.url)
        alice = User.objects.get(username="alice")
        self.assertFalse(alice.is_active)  # gated until verified
        self.assertTrue(Profile.objects.filter(user=alice).exists())
        # Verification email sent.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Confirm", mail.outbox[0].subject)
        # Inactive user can't log in yet.
        self.assertFalse(self.client.login(username="alice", password="hunter22test!"))

    def test_verify_email_activates_and_logs_in(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.create_user("bob", email="b@x.com", password="pw12345678", is_active=False)
        Profile.objects.get_or_create(user=user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        r = self.client.get(reverse("accounts:verify_email", kwargs={"uidb64": uid, "token": token}))
        self.assertEqual(r.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_verify_email_bad_token_rejected(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.create_user("carl", email="c@x.com", password="pw12345678", is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        r = self.client.get(reverse("accounts:verify_email",
                                    kwargs={"uidb64": uid, "token": "bogus-token"}))
        self.assertEqual(r.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_dashboard_requires_login(self):
        r = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)

    def test_dashboard_survives_missing_profile(self):
        """Regression: legacy users without Profile used to 500."""
        u = User.objects.create_user("legacy", password="pw12345678")
        Profile.objects.filter(user=u).delete()  # force the bug condition
        self.client.force_login(u)
        r = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Profile.objects.filter(user=u).exists())  # auto-healed


# ---------------- Courses: enrollment + gating ----------------

class EnrollmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("bob", password="pw12345678")
        self.free_course, _, self.free_lesson = make_course(is_free=True)
        self.free_course.slug = "free-course"; self.free_course.save()
        self.paid_course, _, self.paid_lesson = make_course()
        self.paid_course.slug = "paid-course"; self.paid_course.save()

    def test_free_course_enroll_redirects_to_lesson(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("courses:enroll", kwargs={"slug": "free-course"}))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/m/", r.url)
        self.assertTrue(Enrollment.objects.filter(user=self.user).exists())

    def test_paid_course_without_subscription_redirects_to_pricing(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("courses:enroll", kwargs={"slug": "paid-course"}))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/subscriptions/", r.url)

    def test_lesson_note_save_and_clear(self):
        self.client.force_login(self.user)
        url = reverse("courses:save_note", kwargs={
            "course_slug": "free-course",
            "module_id": self.free_lesson.module_id,
            "lesson_slug": "l1",
        })
        self.client.post(url, {"body": "key takeaway"})
        self.assertEqual(LessonNote.objects.get(user=self.user).body, "key takeaway")
        self.client.post(url, {"body": ""})
        self.assertFalse(LessonNote.objects.filter(user=self.user).exists())


# ---------------- Reviews ----------------

class ReviewTests(TestCase):
    def test_only_enrolled_users_can_review(self):
        user = User.objects.create_user("cora", password="pw12345678")
        course, _, _ = make_course(is_free=True)
        self.client.force_login(user)

        # Not enrolled → review should be rejected (redirect + no row created).
        self.client.post(reverse("courses:post_review", kwargs={"slug": course.slug}),
                         {"rating": 5, "body": "fake"})
        self.assertFalse(CourseReview.objects.exists())

        # Enroll, then review goes through.
        Enrollment.objects.create(user=user, course=course)
        self.client.post(reverse("courses:post_review", kwargs={"slug": course.slug}),
                         {"rating": 4, "body": "solid"})
        self.assertEqual(CourseReview.objects.get().rating, 4)


# ---------------- Coupons ----------------

class CouponTests(TestCase):
    def test_coupon_discounts_price(self):
        c = Coupon.objects.create(code="SAVE10", percent_off=10)
        self.assertEqual(c.apply(Decimal("1000")), Decimal("900.00"))

    def test_coupon_scoped_to_other_plan_rejected(self):
        pro = Plan.objects.create(name="Pro", slug="pro", price_npr=Decimal("999"),
                                  interval="monthly", duration_days=30, is_active=True)
        lite = Plan.objects.create(name="Lite", slug="lite", price_npr=Decimal("199"),
                                   interval="monthly", duration_days=30, is_active=True)
        c = Coupon.objects.create(code="PROONLY", percent_off=20)
        c.plans.add(pro)
        # Valid on Pro...
        self.assertTrue(c.is_valid(plan=pro))
        # ...invalid on Lite.
        self.assertFalse(c.is_valid(plan=lite))

        user = User.objects.create_user("kai", password="pw12345678")
        self.client.force_login(user)
        r = self.client.get(reverse("subscriptions:checkout", kwargs={"slug": "lite"}),
                            {"code": "PROONLY"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "invalid or expired")

    def test_invalid_coupon_is_ignored(self):
        Coupon.objects.create(code="DEAD", percent_off=50, is_active=False)
        user = User.objects.create_user("dana", password="pw12345678")
        Plan.objects.create(name="Pro", slug="pro", price_npr=Decimal("999"),
                            interval="monthly", duration_days=30, is_active=True)
        self.client.force_login(user)
        r = self.client.get(reverse("subscriptions:checkout", kwargs={"slug": "pro"}),
                            {"code": "DEAD"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "invalid or expired")


# ---------------- Payments: callback hardening ----------------

class PaymentCallbackTests(TestCase):
    """
    The sandbox success callbacks must:
      - activate a subscription on first valid hit,
      - be idempotent (second hit doesn't re-activate),
      - refuse when PAYMENT_SANDBOX is off (prevents forged prod URLs).
    """
    def setUp(self):
        self.user = User.objects.create_user("fay", password="pw12345678")
        self.plan = Plan.objects.create(
            name="Pro", slug="pro", price_npr=Decimal("999"),
            interval="monthly", duration_days=30, is_active=True,
        )
        self.sub = Subscription.objects.create(user=self.user, plan=self.plan, status="pending")
        self.payment = Payment.objects.create(
            subscription=self.sub, gateway="esewa", amount=Decimal("999"),
            currency="NPR", reference="TXN-TEST123", status="initiated",
        )
        self.client.force_login(self.user)

    def test_sandbox_success_activates_once(self):
        r = self.client.get(reverse("subscriptions:esewa_success"), {"ref": "TXN-TEST123"})
        self.assertEqual(r.status_code, 302)
        self.payment.refresh_from_db(); self.sub.refresh_from_db()
        self.assertEqual(self.payment.status, "success")
        self.assertEqual(self.sub.status, "active")

    def test_callback_is_idempotent(self):
        self.client.get(reverse("subscriptions:esewa_success"), {"ref": "TXN-TEST123"})
        # Second hit should NOT re-activate or change anything destructive.
        self.client.get(reverse("subscriptions:esewa_success"), {"ref": "TXN-TEST123"})
        self.assertEqual(Payment.objects.filter(reference="TXN-TEST123").count(), 1)

    @override_settings(PAYMENT_SANDBOX=False)
    def test_stub_success_refused_in_production(self):
        r = self.client.get(reverse("subscriptions:esewa_success"), {"ref": "TXN-TEST123"})
        self.assertEqual(r.status_code, 302)
        self.payment.refresh_from_db(); self.sub.refresh_from_db()
        # Still initiated — forged URL didn't activate anything.
        self.assertEqual(self.payment.status, "initiated")
        self.assertNotEqual(self.sub.status, "active")


# ---------------- eSewa HMAC verification ----------------

class EsewaHMACTests(TestCase):
    def test_signature_roundtrip(self):
        data = {"total_amount": "999", "transaction_uuid": "TXN-X", "product_code": "EPAYTEST"}
        sig = esewa_signature(data)
        self.assertTrue(verify_esewa_signature(data, sig))

    def test_tampered_amount_rejected(self):
        data = {"total_amount": "999", "transaction_uuid": "TXN-X", "product_code": "EPAYTEST"}
        sig = esewa_signature(data)
        tampered = {**data, "total_amount": "1"}  # attacker tries to pay less
        self.assertFalse(verify_esewa_signature(tampered, sig))

    def test_empty_signature_rejected(self):
        data = {"total_amount": "999", "transaction_uuid": "TXN-X", "product_code": "EPAYTEST"}
        self.assertFalse(verify_esewa_signature(data, ""))


class EsewaVerifiedCallbackTests(TestCase):
    """The HMAC-verified path must work even with PAYMENT_SANDBOX off."""
    def setUp(self):
        self.user = User.objects.create_user("hank", email="h@x.com", password="pw12345678")
        self.plan = Plan.objects.create(
            name="Pro", slug="pro", price_npr=Decimal("999"),
            interval="monthly", duration_days=30, is_active=True,
        )
        self.sub = Subscription.objects.create(user=self.user, plan=self.plan, status="pending")
        self.payment = Payment.objects.create(
            subscription=self.sub, gateway="esewa", amount=Decimal("999"),
            currency="NPR", reference="TXN-HANK1", status="initiated",
        )
        self.client.force_login(self.user)

    @override_settings(PAYMENT_SANDBOX=False, PAYMENT_GATEWAYS={
        "esewa": {"merchant_id": "EPAYTEST", "secret_key": "test-secret"},
    })
    def test_valid_signature_activates_in_production(self):
        data = {"total_amount": "999", "transaction_uuid": "TXN-HANK1", "product_code": "EPAYTEST"}
        sig = esewa_signature(data)
        r = self.client.get(reverse("subscriptions:esewa_success"), {**data, "signature": sig})
        self.assertEqual(r.status_code, 302)
        self.payment.refresh_from_db(); self.sub.refresh_from_db()
        self.assertEqual(self.payment.status, "success")
        self.assertEqual(self.sub.status, "active")

    @override_settings(PAYMENT_SANDBOX=False, PAYMENT_GATEWAYS={
        "esewa": {"merchant_id": "EPAYTEST", "secret_key": "test-secret"},
    })
    def test_bad_signature_refused(self):
        data = {"total_amount": "999", "transaction_uuid": "TXN-HANK1", "product_code": "EPAYTEST"}
        r = self.client.get(reverse("subscriptions:esewa_success"), {**data, "signature": "deadbeef"})
        self.assertEqual(r.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "initiated")


# ---------------- Khalti verified callback ----------------

class KhaltiVerifiedCallbackTests(TestCase):
    """Khalti redirects back with a `pidx`; we call /epayment/lookup/ to verify.

    Network calls are patched — we never touch the real Khalti API from tests.
    """
    def setUp(self):
        self.user = User.objects.create_user("kara", email="k@x.com", password="pw12345678")
        self.plan = Plan.objects.create(
            name="Pro", slug="pro", price_npr=Decimal("999"),
            interval="monthly", duration_days=30, is_active=True,
        )
        self.sub = Subscription.objects.create(user=self.user, plan=self.plan, status="pending")
        self.payment = Payment.objects.create(
            subscription=self.sub, gateway="khalti", amount=Decimal("999"),
            currency="NPR", reference="TXN-KARA1", status="initiated",
        )
        self.client.force_login(self.user)

    def _url(self):
        return reverse("subscriptions:khalti_verify", kwargs={"payment_id": self.payment.id})

    def test_completed_lookup_activates_subscription(self):
        from unittest.mock import patch
        with patch("apps.subscriptions.views.verify_khalti_payment",
                   return_value={"status": "Completed", "total_amount": 99900,
                                 "transaction_id": "abc123"}):
            r = self.client.get(self._url(), {"pidx": "good-pidx"})
        self.assertEqual(r.status_code, 302)
        self.payment.refresh_from_db(); self.sub.refresh_from_db()
        self.assertEqual(self.payment.status, "success")
        self.assertEqual(self.sub.status, "active")

    def test_failed_lookup_refuses_activation(self):
        from unittest.mock import patch
        with patch("apps.subscriptions.views.verify_khalti_payment", return_value=None):
            r = self.client.get(self._url(), {"pidx": "bad-pidx"})
        self.assertEqual(r.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "initiated")

    @override_settings(PAYMENT_SANDBOX=False)
    def test_no_pidx_refused_in_production(self):
        # Falls into the stub branch, which _confirm_payment refuses when sandbox=off.
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "initiated")


# ---------------- Email receipt ----------------

class ReceiptEmailTests(TestCase):
    def test_receipt_email_sent_on_sandbox_activation(self):
        user = User.objects.create_user("ivy", email="ivy@x.com", password="pw12345678")
        plan = Plan.objects.create(name="Pro", slug="pro", price_npr=Decimal("999"),
                                   interval="monthly", duration_days=30, is_active=True)
        sub = Subscription.objects.create(user=user, plan=plan, status="pending")
        payment = Payment.objects.create(
            subscription=sub, gateway="esewa", amount=Decimal("999"),
            currency="NPR", reference="TXN-IVY", status="initiated",
        )
        self.client.force_login(user)
        mail.outbox = []
        self.client.get(reverse("subscriptions:esewa_success"), {"ref": "TXN-IVY"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Pro", mail.outbox[0].subject)
        self.assertIn("TXN-IVY", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ["ivy@x.com"])


# ---------------- Refund flow ----------------

class RefundTests(TestCase):
    def test_refund_marks_payment_and_expires_subscription(self):
        user = User.objects.create_user("jade", password="pw12345678")
        plan = Plan.objects.create(name="Pro", slug="pro", price_npr=Decimal("999"),
                                   interval="monthly", duration_days=30, is_active=True)
        sub = Subscription.objects.create(user=user, plan=plan, status="pending")
        sub.activate()
        payment = Payment.objects.create(
            subscription=sub, gateway="esewa", amount=Decimal("999"),
            currency="NPR", reference="TXN-JADE", status="success",
        )
        self.assertTrue(refund_payment(payment, reason="test"))
        payment.refresh_from_db(); sub.refresh_from_db()
        self.assertEqual(payment.status, "refunded")
        self.assertEqual(sub.status, "expired")
        # Idempotent second call.
        self.assertFalse(refund_payment(payment))
        # Can't refund non-success.
        pending = Payment.objects.create(
            subscription=sub, gateway="esewa", amount=Decimal("999"),
            currency="NPR", reference="TXN-PEND", status="initiated",
        )
        with self.assertRaises(ValueError):
            refund_payment(pending)


# ---------------- Subscription self-service ----------------

class SubscriptionManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("gina", password="pw12345678")
        self.plan = Plan.objects.create(
            name="Pro", slug="pro", price_npr=Decimal("999"),
            interval="monthly", duration_days=30, is_active=True,
        )
        self.sub = Subscription.objects.create(user=self.user, plan=self.plan, status="pending")
        self.sub.activate()  # now active with expires_at set
        self.payment = Payment.objects.create(
            subscription=self.sub, gateway="khalti", amount=Decimal("999"),
            currency="NPR", reference="TXN-GINA1", status="success",
        )
        self.client.force_login(self.user)

    def test_my_subscription_page_lists_plan_and_payment(self):
        r = self.client.get(reverse("subscriptions:my_subscription"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Pro")
        self.assertContains(r, "Khalti")
        self.assertContains(r, reverse("subscriptions:receipt", kwargs={"payment_id": self.payment.id}))

    def test_cancel_subscription_flips_status_but_keeps_payment(self):
        r = self.client.post(reverse("subscriptions:cancel_subscription", kwargs={"pk": self.sub.pk}))
        self.assertEqual(r.status_code, 302)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, "cancelled")
        # Second cancel is rejected (idempotency / safety).
        r2 = self.client.post(reverse("subscriptions:cancel_subscription", kwargs={"pk": self.sub.pk}))
        self.assertEqual(r2.status_code, 302)  # redirected with error message
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, "cancelled")

    def test_cannot_cancel_someone_elses_subscription(self):
        other = User.objects.create_user("mallory", password="pw12345678")
        self.client.force_login(other)
        r = self.client.post(reverse("subscriptions:cancel_subscription", kwargs={"pk": self.sub.pk}))
        self.assertEqual(r.status_code, 404)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, "active")

    def test_receipt_accessible_to_owner_only(self):
        r = self.client.get(reverse("subscriptions:receipt", kwargs={"payment_id": self.payment.id}))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "TXN-GINA1")
        self.assertContains(r, "Total paid")

        other = User.objects.create_user("snoop", password="pw12345678")
        self.client.force_login(other)
        r = self.client.get(reverse("subscriptions:receipt", kwargs={"payment_id": self.payment.id}))
        self.assertEqual(r.status_code, 404)


# ---------------- Certificate gating ----------------

class CertificateTests(TestCase):
    def test_incomplete_course_redirects(self):
        user = User.objects.create_user("eve", password="pw12345678")
        course, _, _ = make_course(is_free=True)
        Enrollment.objects.create(user=user, course=course)
        self.client.force_login(user)
        r = self.client.get(reverse("courses:certificate", kwargs={"slug": course.slug}))
        self.assertEqual(r.status_code, 302)  # redirected back to course

    def test_certificate_pdf_blocked_until_complete(self):
        user = User.objects.create_user("ivy", password="pw12345678")
        course, _, _ = make_course(is_free=True)
        Enrollment.objects.create(user=user, course=course)
        self.client.force_login(user)
        r = self.client.get(reverse("courses:certificate_pdf", kwargs={"slug": course.slug}))
        self.assertEqual(r.status_code, 404)

    def test_certificate_pdf_download_for_staff(self):
        # Staff bypass the progress gate — simplest way to exercise the render path.
        staff = User.objects.create_user("sam", password="pw12345678", is_staff=True)
        course, _, _ = make_course(is_free=True)
        Enrollment.objects.create(user=staff, course=course)
        self.client.force_login(staff)
        r = self.client.get(reverse("courses:certificate_pdf", kwargs={"slug": course.slug}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertIn(f"certificate-{course.slug}.pdf", r["Content-Disposition"])
        self.assertTrue(r.content.startswith(b"%PDF"))


# ---------------- Support chat ----------------

class SupportChatTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_bot_replies_and_escalates(self):
        r = self.client.post(reverse("support:api_send"),
                             data='{"body":"agent please"}',
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "awaiting_agent")
        self.assertTrue(any(m["role"] == "bot" for m in data["messages"]))
        self.assertEqual(SupportThread.objects.count(), 1)

    def test_empty_message_rejected(self):
        r = self.client.post(reverse("support:api_send"),
                             data='{"body":""}',
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)


# ---------------- Rate limiting ----------------

@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_chat_rate_limited_after_burst(self):
        url = reverse("support:api_send")
        for _ in range(20):
            self.client.post(url, data='{"body":"hi"}', content_type="application/json")
        r = self.client.post(url, data='{"body":"hi"}', content_type="application/json")
        self.assertEqual(r.status_code, 429)


# ---------------- Staff dashboard access control ----------------

class StaffDashboardTests(TestCase):
    def test_requires_staff(self):
        User.objects.create_user("noob", password="pw12345678")
        self.client.login(username="noob", password="pw12345678")
        r = self.client.get(reverse("core:staff_dashboard"))
        self.assertIn(r.status_code, (302, 403))  # admin's staff_member_required kicks to login

    def test_staff_sees_dashboard(self):
        s = User.objects.create_user("boss", password="pw12345678", is_staff=True)
        self.client.force_login(s)
        r = self.client.get(reverse("core:staff_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Platform at a glance")


# ---------------- Instructor workspace ----------------

class InstructorWorkspaceTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("teach", password="pw12345678")
        Profile.objects.filter(user=self.teacher).update(role="instructor")
        self.student = User.objects.create_user("stud", password="pw12345678")
        self.cat, _ = Category.objects.get_or_create(
            slug="entrance-test",
            defaults={"name": "Entrance Test", "pillar": "entrance"},
        )

    def test_non_instructor_is_denied(self):
        self.client.force_login(self.student)
        r = self.client.get(reverse("courses:instructor_dashboard"))
        # Gated: decorator redirects to the denied page.
        self.assertEqual(r.status_code, 302)
        self.assertIn("/teach/denied/", r.url)

    def test_anonymous_redirected_to_login(self):
        r = self.client.get(reverse("courses:instructor_dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)

    def test_instructor_can_create_course_module_lesson(self):
        self.client.force_login(self.teacher)
        # Create course
        r = self.client.post(reverse("courses:instructor_course_create"), {
            "category": self.cat.id, "title": "My Course", "tagline": "hook",
            "description": "desc", "difficulty": "scratch", "duration_weeks": 4,
            "price_npr": "500", "is_free": "", "published": "",
        })
        self.assertEqual(r.status_code, 302)
        course = Course.objects.get(title="My Course")
        # New courses default to unpublished for QA safety.
        self.assertFalse(course.published)
        self.assertEqual(course.instructor.user, self.teacher)

        # Create module
        r = self.client.post(
            reverse("courses:instructor_module_create", kwargs={"course_slug": course.slug}),
            {"title": "M1", "summary": "intro", "order": 1},
        )
        self.assertEqual(r.status_code, 302)
        module = Module.objects.get(course=course, title="M1")

        # Create lesson
        r = self.client.post(
            reverse("courses:instructor_lesson_create",
                    kwargs={"course_slug": course.slug, "module_id": module.id}),
            {"title": "L1", "kind": "article", "video_url": "",
             "body": "content", "duration_minutes": 10, "order": 1},
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Lesson.objects.filter(module=module, title="L1").exists())

    def test_instructor_cannot_touch_another_instructors_course(self):
        # Teacher A creates a course
        self.client.force_login(self.teacher)
        self.client.post(reverse("courses:instructor_course_create"), {
            "category": self.cat.id, "title": "Mine", "tagline": "",
            "description": "d", "difficulty": "scratch", "duration_weeks": 4,
            "price_npr": "500",
        })
        course = Course.objects.get(title="Mine")

        # Teacher B exists
        other = User.objects.create_user("teach2", password="pw12345678")
        Profile.objects.filter(user=other).update(role="instructor")
        self.client.force_login(other)

        # B tries to edit A's course → 404 (not 403 — we don't reveal existence).
        r = self.client.get(reverse("courses:instructor_course_edit", kwargs={"slug": course.slug}))
        self.assertEqual(r.status_code, 404)
        # B tries to toggle publish on A's course → also 404.
        r = self.client.post(reverse("courses:instructor_course_publish", kwargs={"slug": course.slug}))
        self.assertEqual(r.status_code, 404)

    def test_video_upload_rejects_oversize(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.courses.instructor.forms import LessonForm

        # 11 MB of zeroes — over the cap we set for the test.
        fake = SimpleUploadedFile("big.mp4", b"\0" * (11 * 1024 * 1024), content_type="video/mp4")
        with override_settings(INSTRUCTOR_MAX_VIDEO_MB=10):
            form = LessonForm(
                data={"title": "L", "kind": "video", "body": "", "duration_minutes": 5, "order": 1},
                files={"video_file": fake},
            )
            self.assertFalse(form.is_valid())
            self.assertIn("video_file", form.errors)

    def test_resource_upload_rejects_bad_mime(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.courses.instructor.forms import LessonResourceForm

        exe = SimpleUploadedFile("evil.exe", b"MZ\x90\x00", content_type="application/x-msdownload")
        form = LessonResourceForm(
            data={"title": "x", "kind": "pdf", "is_free_preview": "", "order": 1},
            files={"file": exe},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_preview_token_shows_unpublished_course(self):
        from apps.courses.instructor.permissions import make_preview_token
        course = Course.objects.create(
            category=self.cat, title="Draft", slug="draft",
            description="d", price_npr=Decimal("0"), is_free=True, published=False,
        )
        # Anonymous with no token → 404.
        r = self.client.get(reverse("courses:detail", kwargs={"slug": "draft"}))
        self.assertEqual(r.status_code, 404)
        # With a valid preview token → 200.
        token = make_preview_token(course)
        r = self.client.get(reverse("courses:detail", kwargs={"slug": "draft"}),
                            {"preview": token})
        self.assertEqual(r.status_code, 200)
        # Tampered token → still 404.
        r = self.client.get(reverse("courses:detail", kwargs={"slug": "draft"}),
                            {"preview": token + "x"})
        self.assertEqual(r.status_code, 404)

    def test_students_page_scoped_to_own_courses(self):
        # Teacher A has a student.
        self.client.force_login(self.teacher)
        course = Course.objects.create(
            category=self.cat, title="A's course", slug="as-course",
            instructor=Instructor.objects.create(user=self.teacher, name="A", slug="a"),
            description="d", price_npr=Decimal("0"), is_free=True, published=True,
        )
        learner = User.objects.create_user("uniquelearner42", password="pw12345678")
        Enrollment.objects.create(user=learner, course=course)
        r = self.client.get(reverse("courses:instructor_students"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "uniquelearner42")

        # Teacher B sees no one.
        other = User.objects.create_user("teach2", password="pw12345678")
        Profile.objects.filter(user=other).update(role="instructor")
        self.client.force_login(other)
        r = self.client.get(reverse("courses:instructor_students"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "uniquelearner42")

    def test_first_publish_goes_through_review_queue(self):
        """New instructor courses must be approved by staff before going live."""
        self.client.force_login(self.teacher)
        self.client.post(reverse("courses:instructor_course_create"), {
            "category": self.cat.id, "title": "Review me", "description": "d",
            "difficulty": "scratch", "duration_weeks": 4, "price_npr": "0", "is_free": "on",
        })
        course = Course.objects.get(title="Review me")
        self.assertEqual(course.review_status, "draft")

        # Hitting Publish submits for review (not live yet).
        self.client.post(reverse("courses:instructor_course_publish", kwargs={"slug": course.slug}))
        course.refresh_from_db()
        self.assertEqual(course.review_status, "pending")
        self.assertFalse(course.published)
        self.assertIsNotNone(course.submitted_at)

        # Staff approves → course is live and freely toggle-able.
        staff = User.objects.create_user("edit", password="pw12345678", is_staff=True)
        self.client.force_login(staff)
        r = self.client.post(reverse("courses:review_approve", kwargs={"slug": course.slug}))
        self.assertEqual(r.status_code, 302)
        course.refresh_from_db()
        self.assertEqual(course.review_status, "approved")
        self.assertTrue(course.published)
        self.assertIsNotNone(course.approved_at)

        # After approval, instructor can unpublish and republish at will.
        self.client.force_login(self.teacher)
        self.client.post(reverse("courses:instructor_course_publish", kwargs={"slug": course.slug}))
        course.refresh_from_db()
        self.assertFalse(course.published)  # unpublished, still approved

    def test_staff_can_request_changes(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse("courses:instructor_course_create"), {
            "category": self.cat.id, "title": "Needs work", "description": "d",
            "difficulty": "scratch", "duration_weeks": 4, "price_npr": "0", "is_free": "on",
        })
        course = Course.objects.get(title="Needs work")
        self.client.post(reverse("courses:instructor_course_publish", kwargs={"slug": course.slug}))

        staff = User.objects.create_user("edit", password="pw12345678", is_staff=True)
        self.client.force_login(staff)
        self.client.post(reverse("courses:review_request_changes", kwargs={"slug": course.slug}),
                         {"notes": "Add more lessons"})
        course.refresh_from_db()
        self.assertEqual(course.review_status, "changes_requested")
        self.assertIn("more lessons", course.review_notes)
        self.assertFalse(course.published)

    def test_review_queue_requires_staff(self):
        self.client.force_login(self.teacher)
        r = self.client.get(reverse("courses:review_queue"))
        # staff_member_required bounces non-staff to admin login.
        self.assertIn(r.status_code, (302, 403))

    def _submit_course(self, title="Mail me"):
        self.teacher.email = "teach@example.com"
        self.teacher.save()
        self.client.force_login(self.teacher)
        self.client.post(reverse("courses:instructor_course_create"), {
            "category": self.cat.id, "title": title, "description": "d",
            "difficulty": "scratch", "duration_weeks": 4, "price_npr": "0", "is_free": "on",
        })
        course = Course.objects.get(title=title)
        self.client.post(reverse("courses:instructor_course_publish",
                                 kwargs={"slug": course.slug}))
        return course

    def test_approve_emails_instructor(self):
        course = self._submit_course("Approve me")
        staff = User.objects.create_user("edapprove", password="pw12345678", is_staff=True)
        self.client.force_login(staff)
        mail.outbox = []
        self.client.post(reverse("courses:review_approve", kwargs={"slug": course.slug}))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("teach@example.com", mail.outbox[0].to)
        self.assertIn("approved", mail.outbox[0].subject.lower())

    def test_request_changes_emails_instructor_with_notes(self):
        course = self._submit_course("Fix me")
        staff = User.objects.create_user("edchanges", password="pw12345678", is_staff=True)
        self.client.force_login(staff)
        mail.outbox = []
        self.client.post(reverse("courses:review_request_changes", kwargs={"slug": course.slug}),
                         {"notes": "Add more lessons"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("teach@example.com", mail.outbox[0].to)
        self.assertIn("Add more lessons", mail.outbox[0].body)


# ---------------- Exams ----------------

class ExamTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("taker", password="pw12345678")
        self.exam = Exam.objects.create(
            name="CMAT Mock", exam_type="cmat", duration_minutes=60,
            requires_subscription=True, is_free_preview=True, published=True,
        )
        # Two questions — Q1 has a correct C1, Q2 has a correct C2.
        self.q1 = Question.objects.create(exam=self.exam, text="2+2?", order=1)
        self.q1_a = Choice.objects.create(question=self.q1, text="4", is_correct=True, order=1)
        self.q1_b = Choice.objects.create(question=self.q1, text="5", is_correct=False, order=2)
        self.q2 = Question.objects.create(exam=self.exam, text="Capital of Nepal?", order=2)
        self.q2_a = Choice.objects.create(question=self.q2, text="Pokhara", is_correct=False, order=1)
        self.q2_b = Choice.objects.create(question=self.q2, text="Kathmandu", is_correct=True, order=2)

    def test_list_and_detail_load(self):
        self.assertEqual(self.client.get(reverse("exams:list")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("exams:detail", kwargs={"slug": self.exam.slug})).status_code,
            200,
        )

    def test_anonymous_cannot_start(self):
        r = self.client.get(reverse("exams:start", kwargs={"slug": self.exam.slug}))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)

    def test_free_preview_is_startable_without_sub(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("exams:start", kwargs={"slug": self.exam.slug}))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/exams/take/", r.url)
        self.assertEqual(ExamAttempt.objects.filter(user=self.user).count(), 1)

    def test_paid_exam_requires_subscription(self):
        self.exam.is_free_preview = False
        self.exam.save()
        self.client.force_login(self.user)
        r = self.client.get(reverse("exams:start", kwargs={"slug": self.exam.slug}))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/subscriptions/", r.url)

    def test_plan_scoped_exam_rejects_wrong_plan(self):
        """An exam keyed to cmat-pro shouldn't unlock for a generic tech-basic sub."""
        self.exam.is_free_preview = False
        self.exam.required_plan_slug = "cmat-pro"
        self.exam.save()
        tech = Plan.objects.create(name="Tech Basic", slug="tech-basic", price_npr=Decimal("500"))
        Subscription.objects.create(user=self.user, plan=tech, status="active")
        self.client.force_login(self.user)
        r = self.client.get(reverse("exams:start", kwargs={"slug": self.exam.slug}))
        self.assertIn("/subscriptions/", r.url)

        # Same user, right plan — gets in.
        cmat = Plan.objects.create(name="CMAT Pro", slug="cmat-pro", price_npr=Decimal("800"))
        Subscription.objects.create(user=self.user, plan=cmat, status="active")
        r = self.client.get(reverse("exams:start", kwargs={"slug": self.exam.slug}))
        self.assertIn("/exams/take/", r.url)

    def test_start_twice_reuses_in_progress_attempt(self):
        self.client.force_login(self.user)
        self.client.get(reverse("exams:start", kwargs={"slug": self.exam.slug}))
        self.client.get(reverse("exams:start", kwargs={"slug": self.exam.slug}))
        self.assertEqual(ExamAttempt.objects.filter(user=self.user).count(), 1)

    def test_submission_grades_correctly(self):
        attempt = ExamAttempt.objects.create(user=self.user, exam=self.exam, total=2)
        self.client.force_login(self.user)
        r = self.client.post(
            reverse("exams:submit", kwargs={"attempt_id": attempt.id}),
            {f"question_{self.q1.id}": self.q1_a.id,  # correct
             f"question_{self.q2.id}": self.q2_a.id}, # wrong
        )
        self.assertEqual(r.status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")
        self.assertEqual(attempt.score, 1)
        self.assertEqual(attempt.total, 2)
        self.assertEqual(attempt.percentage, 50.0)

    def test_take_page_does_not_leak_correct_answer(self):
        attempt = ExamAttempt.objects.create(user=self.user, exam=self.exam, total=2)
        self.q1.explanation = "Basic arithmetic — two plus two equals four."
        self.q1.save()
        self.client.force_login(self.user)
        r = self.client.get(reverse("exams:take", kwargs={"attempt_id": attempt.id}))
        self.assertEqual(r.status_code, 200)
        # Neither the explanation nor any is_correct signal should appear pre-submission.
        self.assertNotContains(r, "Basic arithmetic")
        self.assertNotContains(r, "is_correct")

    def test_leaderboard_loads(self):
        r = self.client.get(reverse("exams:leaderboard", kwargs={"slug": self.exam.slug}))
        self.assertEqual(r.status_code, 200)


# ---------------- Instructor directory ----------------

class InstructorPageTests(TestCase):
    def test_directory_and_detail(self):
        Instructor.objects.create(name="Prof X", slug="prof-x", headline="Mentor")
        self.assertEqual(self.client.get(reverse("core:instructors")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("courses:instructor_detail",
                                    kwargs={"slug": "prof-x"})).status_code,
            200,
        )
