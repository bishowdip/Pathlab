from django.contrib import admin

from .models import SupportMessage, SupportThread


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0
    fields = ("role", "author", "body", "created_at")
    readonly_fields = ("created_at",)


@admin.register(SupportThread)
class SupportThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "guest_email", "status", "assigned_agent", "updated_at")
    list_filter = ("status",)
    search_fields = ("user__username", "guest_email", "subject")
    inlines = [SupportMessageInline]
    readonly_fields = ("created_at", "updated_at", "session_key")


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ("thread", "role", "author", "created_at")
    list_filter = ("role",)
    search_fields = ("body",)
