from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Plan(models.Model):
    INTERVAL_CHOICES = [
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("yearly", "Yearly"),
        ("lifetime", "Lifetime"),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    price_npr = models.DecimalField(max_digits=10, decimal_places=2)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    interval = models.CharField(max_length=20, choices=INTERVAL_CHOICES, default="monthly")
    duration_days = models.PositiveIntegerField(
        default=30, help_text="Access length; ignored for lifetime."
    )
    features = models.TextField(
        blank=True, help_text="One feature per line — rendered as bullet list."
    )
    is_popular = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "price_npr"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def feature_list(self):
        return [f.strip() for f in self.features.splitlines() if f.strip()]

    def __str__(self):
        return f"{self.name} (NPR {self.price_npr})"


class Coupon(models.Model):
    """Promo code granting a % discount on plan prices."""
    code = models.CharField(max_length=40, unique=True)
    description = models.CharField(max_length=200, blank=True)
    percent_off = models.PositiveSmallIntegerField(
        default=10, help_text="0–100 — percentage discount."
    )
    max_redemptions = models.PositiveIntegerField(
        default=0, help_text="0 = unlimited."
    )
    plans = models.ManyToManyField(
        "Plan", blank=True, related_name="coupons",
        help_text="Restrict to specific plans. Leave empty to apply to all plans.",
    )
    times_redeemed = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self, plan=None):
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        if self.max_redemptions and self.times_redeemed >= self.max_redemptions:
            return False
        # Plan scoping: if any plans are listed, the checkout plan must be one of them.
        if plan is not None and self.pk:
            scoped = self.plans.all()
            if scoped.exists() and plan not in scoped:
                return False
        return True

    def apply(self, price):
        """Return the discounted price (Decimal-safe)."""
        from decimal import Decimal
        pct = Decimal(self.percent_off) / Decimal(100)
        return (price * (Decimal(1) - pct)).quantize(Decimal("0.01"))

    def __str__(self):
        return f"{self.code} (-{self.percent_off}%)"


class Subscription(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending payment"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    coupon = models.ForeignKey(
        "Coupon", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="subscriptions",
    )
    discounted_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Final charged price after coupon. Null = plan's list price.",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def activate(self):
        self.status = "active"
        self.started_at = timezone.now()
        if self.plan.interval != "lifetime":
            self.expires_at = self.started_at + timezone.timedelta(days=self.plan.duration_days)
        self.save()

    def is_active(self):
        if self.status != "active":
            return False
        if self.expires_at and self.expires_at < timezone.now():
            self.status = "expired"
            self.save(update_fields=["status"])
            return False
        return True

    def __str__(self):
        return f"{self.user} — {self.plan.name} ({self.status})"


class Payment(models.Model):
    GATEWAY_CHOICES = [
        ("esewa", "eSewa"),
        ("khalti", "Khalti"),
        ("stripe", "Stripe"),
        ("paypal", "PayPal"),
    ]
    # (PayPal gateway stub is wired in views.)
    STATUS_CHOICES = [
        ("initiated", "Initiated"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="payments"
    )
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default="NPR")
    reference = models.CharField(max_length=120, blank=True, help_text="Gateway txn id")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="initiated")
    raw_response = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.gateway} {self.amount} — {self.status}"
