from django import forms

from apps.courses.models import Course, Lesson, LessonResource, Module

from .validators import validate_resource_upload, validate_video_upload


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        # `published`, `review_status`, `approved_at` are staff-only — they
        # are managed by the editorial review flow and `course_toggle_publish`.
        # `price_npr` / `is_free` stay editable so instructors can set pricing.
        fields = [
            "category", "title", "tagline", "description",
            "difficulty", "duration_weeks",
            "thumbnail", "price_npr", "is_free",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "tagline": forms.TextInput(attrs={"placeholder": "One-line hook shown on cards"}),
        }


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ["title", "summary", "order"]
        widgets = {"summary": forms.Textarea(attrs={"rows": 2})}


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = [
            "title", "kind",
            "video_url", "video_file",
            "body", "duration_minutes",
            "order", "is_free_preview",
        ]
        widgets = {"body": forms.Textarea(attrs={"rows": 8})}

    def clean_video_file(self):
        f = self.cleaned_data.get("video_file")
        validate_video_upload(f)
        return f


class LessonResourceForm(forms.ModelForm):
    class Meta:
        model = LessonResource
        fields = ["title", "kind", "file", "is_free_preview", "order"]

    def clean_file(self):
        f = self.cleaned_data.get("file")
        validate_resource_upload(f)
        return f
