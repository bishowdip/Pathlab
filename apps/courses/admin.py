from django.contrib import admin, messages
from django.utils import timezone

from .services import notify_course_review_decision
from .models import (
    Badge, Category, Course, CourseReview, Enrollment, Instructor,
    Lesson, LessonNote, LessonProgress, LessonResource, Module,
    SuccessStat, Testimonial, UserBadge,
)


@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display = ("name", "headline", "is_featured")
    list_filter = ("is_featured",)
    search_fields = ("name", "headline")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CourseReview)
class CourseReviewAdmin(admin.ModelAdmin):
    list_display = ("course", "user", "rating", "created_at")
    list_filter = ("rating",)
    search_fields = ("course__title", "user__username")


@admin.register(LessonNote)
class LessonNoteAdmin(admin.ModelAdmin):
    list_display = ("lesson", "user", "updated_at")
    search_fields = ("lesson__title", "user__username")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "pillar", "shape", "accent_color", "order")
    list_editable = ("order",)
    list_filter = ("pillar",)
    prepopulated_fields = {"slug": ("name",)}


class TestimonialInline(admin.TabularInline):
    model = Testimonial
    extra = 1


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 1
    show_change_link = True


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "difficulty", "price_npr", "is_featured",
                    "published", "review_status")
    list_filter = ("category__pillar", "difficulty", "is_featured", "published", "review_status")
    search_fields = ("title", "description")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ModuleInline, TestimonialInline]
    actions = ("bulk_approve",)

    @admin.action(description="Approve and publish selected courses")
    def bulk_approve(self, request, queryset):
        approved = skipped = 0
        now = timezone.now()
        for c in queryset:
            if c.review_status == "approved" and c.published:
                skipped += 1
                continue
            c.review_status = "approved"
            c.approved_at = c.approved_at or now
            c.published = True
            c.review_notes = ""
            c.save(update_fields=["review_status", "approved_at", "published", "review_notes"])
            notify_course_review_decision(c, "approved")
            approved += 1
        self.message_user(
            request,
            f"Approved {approved} course{'s' if approved != 1 else ''}; skipped {skipped} already-live.",
            level=messages.SUCCESS,
        )


class LessonResourceInline(admin.TabularInline):
    model = LessonResource
    extra = 1
    fields = ("order", "title", "kind", "file", "is_free_preview")


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    fields = ("order", "title", "kind", "duration_minutes", "is_free_preview", "video_url", "video_file")
    show_change_link = True


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "order")
    list_filter = ("course",)
    inlines = [LessonInline]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "kind", "duration_minutes", "is_free_preview", "order")
    list_filter = ("kind", "is_free_preview", "module__course")
    search_fields = ("title",)
    inlines = [LessonResourceInline]
    fieldsets = (
        (None, {
            "fields": ("module", "title", "slug", "kind", "order",
                       "duration_minutes", "is_free_preview"),
        }),
        ("Content", {
            "fields": ("video_url", "video_file", "body"),
            "description": "Use either an embed URL (YouTube/Vimeo) or upload a video file. "
                           "Body supports rich text for article lessons.",
        }),
    )


@admin.register(LessonResource)
class LessonResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "lesson", "kind", "is_free_preview", "uploaded_at")
    list_filter = ("kind", "is_free_preview")
    search_fields = ("title", "lesson__title")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "started_at", "completed_at")
    list_filter = ("course",)
    search_fields = ("user__username", "course__title")


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "lesson", "completed", "completed_at")
    list_filter = ("completed",)


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "icon_shape")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ("user", "badge", "awarded_at")
    search_fields = ("user__username", "badge__name")


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("student_name", "course", "is_video", "is_featured")
    list_filter = ("is_video", "is_featured")


@admin.register(SuccessStat)
class SuccessStatAdmin(admin.ModelAdmin):
    list_display = ("label", "value", "order")
    list_editable = ("order",)
