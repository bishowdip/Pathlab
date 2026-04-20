from django.conf import settings
from django.db import models


class Profile(models.Model):
    ROLE_CHOICES = [
        ("student", "Student"),
        ("kid", "Kid (Summer Camp)"),
        ("instructor", "Instructor"),
    ]
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="student")
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    country = models.CharField(max_length=50, default="Nepal")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class NewsletterSubscription(models.Model):
    email = models.EmailField(unique=True)
    source = models.CharField(max_length=60, default="footer")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
