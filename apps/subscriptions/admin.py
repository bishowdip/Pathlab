from django.contrib import admin, messages
from .models import Coupon, Payment, Plan, Subscription
from .services import refund_payment


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "percent_off", "times_redeemed", "max_redemptions",
                    "expires_at", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "description")


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "interval", "price_npr", "duration_days", "is_popular", "is_active", "order")
    list_editable = ("order", "is_popular", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "started_at", "expires_at")
    list_filter = ("status", "plan")
    search_fields = ("user__username",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "subscription", "gateway", "amount", "currency", "status", "created_at")
    list_filter = ("gateway", "status")
    search_fields = ("reference", "subscription__user__username")
    readonly_fields = ("created_at",)
    actions = ("refund_selected",)

    @admin.action(description="Refund selected payments (expires subscription)")
    def refund_selected(self, request, queryset):
        refunded = skipped = errors = 0
        for p in queryset:
            try:
                if refund_payment(p, reason=f"admin:{request.user.username}"):
                    refunded += 1
                else:
                    skipped += 1
            except ValueError:
                errors += 1
        self.message_user(
            request,
            f"Refunded {refunded}; already-refunded {skipped}; rejected {errors}.",
            level=messages.SUCCESS if errors == 0 else messages.WARNING,
        )
