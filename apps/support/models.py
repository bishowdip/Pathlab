from django.conf import settings
from django.db import models


class SupportThread(models.Model):
    """A single conversation between a learner and the bot / human agents."""
    STATUS_CHOICES = [
        ("bot", "With bot"),
        ("awaiting_agent", "Waiting on human agent"),
        ("with_agent", "With human agent"),
        ("resolved", "Resolved"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="support_threads", null=True, blank=True,
        help_text="Null for anonymous/guest sessions.",
    )
    guest_email = models.EmailField(blank=True)
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    subject = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="bot")
    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="assigned_support_threads",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        who = self.user.username if self.user else (self.guest_email or "guest")
        return f"#{self.id} · {who} · {self.get_status_display()}"


class SupportMessage(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("bot", "Bot"),
        ("agent", "Human agent"),
        ("system", "System"),
    ]
    thread = models.ForeignKey(
        SupportThread, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="support_messages",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.thread_id} · {self.role} · {self.body[:40]}"
