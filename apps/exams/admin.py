from django.contrib import admin
from .models import Answer, Choice, Exam, ExamAttempt, Question


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "exam", "section", "order")
    list_filter = ("exam", "section")
    search_fields = ("text",)
    inlines = [ChoiceInline]


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 1
    show_change_link = True
    fields = ("text", "section", "order", "explanation")


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = (
        "name", "exam_type", "duration_minutes", "total_questions",
        "requires_subscription", "is_free_preview", "published",
    )
    list_filter = ("exam_type", "requires_subscription", "published")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "exam", "score", "total", "status", "started_at", "submitted_at")
    list_filter = ("status", "exam")
    search_fields = ("user__username", "exam__name")
    readonly_fields = ("started_at", "submitted_at")


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected_choice", "is_correct")
    list_filter = ("is_correct",)
