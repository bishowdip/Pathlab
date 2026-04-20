from django.contrib import admin
from .models import NewsletterSubscription, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "country", "phone")
    list_filter = ("role", "country")
    search_fields = ("user__username", "user__email", "phone")


@admin.register(NewsletterSubscription)
class NewsletterSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("email", "source", "created_at")
    search_fields = ("email",)
    list_filter = ("source",)
