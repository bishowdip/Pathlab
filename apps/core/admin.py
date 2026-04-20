from django.contrib import admin
from .models import SiteSettings, TrustSignal


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("brand_name", "promo_active", "promo_text")


@admin.register(TrustSignal)
class TrustSignalAdmin(admin.ModelAdmin):
    list_display = ("title", "icon", "order")
    list_editable = ("order",)
