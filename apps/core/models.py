from django.db import models


class SiteSettings(models.Model):
    """Singleton-ish: editable homepage hero + promo banner content."""

    brand_name = models.CharField(max_length=80, default="PathLab")
    tagline = models.CharField(
        max_length=200,
        default="The place where your next exam, career, or first line of code begins.",
    )
    hero_title = models.CharField(
        max_length=200,
        default="Your entrance exam, your upskill, your kid's first AI project — one place.",
    )
    hero_subtitle = models.CharField(
        max_length=300,
        default="Built for Nepal. Trusted globally. Clean, fast, non-stuffy.",
    )
    hero_cta_label = models.CharField(max_length=40, default="Try for free")
    promo_active = models.BooleanField(default=True)
    promo_text = models.CharField(max_length=200, default="15% off launch — ends this Friday")
    promo_cta_label = models.CharField(max_length=40, default="Claim discount")
    promo_cta_url = models.CharField(max_length=200, default="/subscriptions/")

    class Meta:
        verbose_name = "Site Setting"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return self.brand_name

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class TrustSignal(models.Model):
    """Used in the 'Why this workshop works' block."""
    title = models.CharField(max_length=100)
    body = models.CharField(max_length=300)
    icon = models.CharField(
        max_length=30, default="spark",
        help_text="shape token: spark, circle, square, triangle",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title
