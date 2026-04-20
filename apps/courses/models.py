from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Category(models.Model):
    """Three pillars: Entrance Prep, Tech Upskilling, Kids' Summer Camp."""

    PILLAR_CHOICES = [
        ("entrance", "Entrance Prep"),
        ("tech", "Tech Upskilling"),
        ("kids", "Kids' Summer Camp"),
    ]
    SHAPE_CHOICES = [
        ("circle", "Circle"),
        ("square", "Square"),
        ("triangle", "Triangle"),
        ("hexagon", "Hexagon"),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    pillar = models.CharField(max_length=20, choices=PILLAR_CHOICES)
    shape = models.CharField(max_length=20, choices=SHAPE_CHOICES, default="circle")
    accent_color = models.CharField(
        max_length=20, default="green",
        help_text="tailwind token: green (Entrance), blue (Tech), neon (Kids)",
    )
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "Categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_pillar_display()})"


class Instructor(models.Model):
    """A teacher who authors courses. Optionally linked to a platform user."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="instructor_profile",
        help_text="Link to a platform account (optional).",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, blank=True)
    headline = models.CharField(max_length=200, blank=True,
                                help_text="One-line professional tagline.")
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to="instructors/", blank=True, null=True)
    linkedin_url = models.URLField(blank=True)
    website_url = models.URLField(blank=True)
    is_featured = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("courses:instructor_detail", kwargs={"slug": self.slug})

    def __str__(self):
        return self.name


class Course(models.Model):
    DIFFICULTY_CHOICES = [
        ("scratch", "From Scratch"),
        ("experienced", "For Experienced"),
        ("kid", "Kid-friendly"),
    ]

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="courses")
    instructor = models.ForeignKey(
        Instructor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="courses",
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    description = models.TextField()
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="scratch")
    duration_weeks = models.PositiveIntegerField(default=4)
    thumbnail = models.ImageField(upload_to="courses/", blank=True, null=True)
    price_npr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_free = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    published = models.BooleanField(default=True)
    # Editorial review: instructors submit → staff approves once; after the first
    # approval, the course can be freely unpublished/republished by its owner.
    REVIEW_CHOICES = [
        ("draft", "Draft"),
        ("pending", "Pending review"),
        ("approved", "Approved"),
        ("changes_requested", "Changes requested"),
    ]
    review_status = models.CharField(
        max_length=20, choices=REVIEW_CHOICES, default="approved",
    )
    review_notes = models.TextField(blank=True, help_text="Staff feedback for the instructor.")
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_featured", "-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("courses:detail", kwargs={"slug": self.slug})

    def __str__(self):
        return self.title

    @property
    def average_rating(self):
        from django.db.models import Avg
        return self.reviews.aggregate(avg=Avg("rating"))["avg"] or 0

    @property
    def review_count(self):
        return self.reviews.count()


class Testimonial(models.Model):
    """Short testimonial bubble attached to a course card (Yandex style)."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="testimonials")
    student_name = models.CharField(max_length=100)
    student_title = models.CharField(max_length=100, blank=True, help_text="e.g. CMAT 2024 topper")
    quote = models.CharField(max_length=280)
    avatar = models.ImageField(upload_to="testimonials/", blank=True, null=True)
    is_video = models.BooleanField(default=False)
    video_url = models.URLField(blank=True)
    is_featured = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.student_name} — {self.course.title}"


class Module(models.Model):
    """A section/chapter of a course."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=150)
    summary = models.CharField(max_length=300, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.course.title} · {self.title}"


class Lesson(models.Model):
    """An individual lesson — video + article body. Kids' camp uses video_url heavily."""
    KIND_CHOICES = [
        ("video", "Video"),
        ("article", "Article"),
        ("project", "Project"),
    ]
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    slug = models.SlugField(blank=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="video")
    video_url = models.URLField(
        blank=True,
        help_text="YouTube/Vimeo embed URL (e.g. https://www.youtube.com/embed/VIDEO_ID)",
    )
    video_file = models.FileField(
        upload_to="lessons/videos/", blank=True, null=True,
        help_text="Optional direct upload. Used if no embed URL is set.",
    )
    body = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=10)
    order = models.PositiveIntegerField(default=0)
    is_free_preview = models.BooleanField(default=False)

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("module", "slug")]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:50]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.module.course.title} · {self.title}"


class LessonResource(models.Model):
    """Downloadable attachments for a lesson (PDFs, slides, source files)."""
    KIND_CHOICES = [
        ("pdf", "PDF"),
        ("slide", "Slides"),
        ("code", "Source / ZIP"),
        ("other", "Other"),
    ]
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name="resources"
    )
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="pdf")
    file = models.FileField(upload_to="lessons/resources/")
    is_free_preview = models.BooleanField(
        default=False,
        help_text="If true, anyone can download — even without a subscription.",
    )
    order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.lesson.title} · {self.title}"


class Enrollment(models.Model):
    """User ↔ Course (auto-created on first lesson view or manual via admin)."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments"
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("user", "course")]
        ordering = ["-started_at"]

    @property
    def progress_percent(self):
        total = Lesson.objects.filter(module__course=self.course).count()
        if not total:
            return 0
        done = LessonProgress.objects.filter(
            enrollment=self, completed=True
        ).count()
        return int(round((done / total) * 100))

    def __str__(self):
        return f"{self.user} → {self.course}"


class CourseReview(models.Model):
    """A 1–5 star rating with written review, one per user per course."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_reviews"
    )
    rating = models.PositiveSmallIntegerField(default=5)  # 1..5
    body = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "course")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} · {self.course} · {self.rating}★"


class LessonNote(models.Model):
    """Private learner notes against a lesson."""
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="notes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_notes"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "lesson")]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user} · {self.lesson.title}"


class LessonProgress(models.Model):
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="lesson_progress"
    )
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress")
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("enrollment", "lesson")]

    def __str__(self):
        return f"{self.enrollment.user} · {self.lesson} · {'done' if self.completed else 'pending'}"


class Badge(models.Model):
    """Gamification for kids' dashboard."""
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True, blank=True)
    description = models.CharField(max_length=200)
    icon_shape = models.CharField(max_length=20, default="circle")
    color = models.CharField(max_length=20, default="kids")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges"
    )
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "badge")]
        ordering = ["-awarded_at"]

    def __str__(self):
        return f"{self.user} → {self.badge}"


class SuccessStat(models.Model):
    """Numbers for the Success Stories homepage block."""
    label = models.CharField(max_length=100)
    value = models.CharField(max_length=50, help_text="e.g. '12,000+' or '94%'")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.value} {self.label}"
