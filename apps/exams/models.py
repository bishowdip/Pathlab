from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Exam(models.Model):
    EXAM_TYPE_CHOICES = [
        ("cmat", "CMAT"),
        ("csit", "BSc CSIT"),
        ("bit", "BIT"),
        ("bca", "BCA"),
        ("bba", "BBA"),
        ("ielts", "IELTS"),
        ("pte", "PTE"),
    ]

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, blank=True)
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPE_CHOICES)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    total_questions = models.PositiveIntegerField(default=50)
    pass_percentage = models.PositiveIntegerField(default=40)
    requires_subscription = models.BooleanField(default=True)
    required_plan_slug = models.SlugField(
        blank=True,
        help_text="Which subscription plan unlocks this exam (e.g. 'cmat-pro').",
    )
    is_free_preview = models.BooleanField(default=False)
    published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["exam_type", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("exams:detail", kwargs={"slug": self.slug})

    def __str__(self):
        return self.name


class Question(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    explanation = models.TextField(
        blank=True,
        help_text="Shown AFTER submission — never leaked to the client during the exam.",
    )
    section = models.CharField(
        max_length=60, blank=True,
        help_text="e.g. 'Verbal', 'Quantitative', 'Reading' (IELTS/PTE).",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"Q{self.order or self.pk}: {self.text[:60]}"


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text[:60]


class ExamAttempt(models.Model):
    STATUS_CHOICES = [
        ("in_progress", "In progress"),
        ("submitted", "Submitted"),
        ("expired", "Expired"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts"
    )
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="in_progress")
    score = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    @property
    def percentage(self):
        if not self.total:
            return 0
        return round((self.score / self.total) * 100, 1)

    @property
    def passed(self):
        return self.percentage >= self.exam.pass_percentage

    @property
    def time_remaining_seconds(self):
        deadline = self.started_at + timezone.timedelta(minutes=self.exam.duration_minutes)
        remaining = (deadline - timezone.now()).total_seconds()
        return max(0, int(remaining))

    def __str__(self):
        return f"{self.user} — {self.exam} ({self.status})"


class Answer(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(Choice, on_delete=models.CASCADE, null=True, blank=True)
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = [("attempt", "question")]
