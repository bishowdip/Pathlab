"""
Instructor workspace — a public (non-admin) UI for course authors to
create courses, modules, lessons, and upload resources. Staff can edit
anything; instructors can only touch their own courses.
"""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from django.db.models import Count

from apps.courses.models import Course, Enrollment
from apps.courses.services import notify_course_review_decision

from .forms import CourseForm, LessonForm, LessonResourceForm, ModuleForm
from .permissions import (
    _owned_course_qs, ensure_instructor_for, get_owned_course,
    get_owned_lesson, get_owned_module, get_owned_resource, instructor_required,
    make_preview_token,
)


def denied(request):
    """Shown when a non-instructor hits the workspace."""
    return render(request, "courses/instructor/denied.html", status=403)


@instructor_required
def students(request):
    """Per-course roster for this instructor's courses."""
    courses = (_owned_course_qs(request.user)
               .annotate(enrolled=Count("enrollments"))
               .order_by("-created_at"))
    # Filter by ?course=<slug> if specified, else show everything.
    active_slug = request.GET.get("course") or ""
    enrollments_qs = (Enrollment.objects
                      .filter(course__in=courses)
                      .select_related("user", "course")
                      .order_by("-started_at"))
    if active_slug:
        enrollments_qs = enrollments_qs.filter(course__slug=active_slug)
    enrollments = list(enrollments_qs[:200])  # cap for safety
    return render(request, "courses/instructor/students.html", {
        "courses": courses, "enrollments": enrollments,
        "active_slug": active_slug, "total": enrollments_qs.count(),
    })


@instructor_required
def dashboard(request):
    instructor = ensure_instructor_for(request.user)
    courses = _owned_course_qs(request.user).select_related("category").order_by("-created_at")
    return render(request, "courses/instructor/dashboard.html",
                  {"instructor": instructor, "courses": courses})


# ---------- Course ----------

@instructor_required
def course_create(request):
    instructor = ensure_instructor_for(request.user)
    if request.method == "POST":
        form = CourseForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.save(commit=False)
            course.instructor = instructor
            # New courses always start as unpublished drafts awaiting review.
            course.published = False
            course.review_status = "draft"
            course.approved_at = None
            course.save()
            messages.success(request, "Course created — now add modules and lessons.")
            return redirect("courses:instructor_course_manage", slug=course.slug)
    else:
        form = CourseForm()
    return render(request, "courses/instructor/course_form.html",
                  {"form": form, "mode": "create"})


@instructor_required
def course_edit(request, slug):
    course = get_owned_course(request.user, slug)
    if request.method == "POST":
        form = CourseForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, "Course updated.")
            return redirect("courses:instructor_course_manage", slug=course.slug)
    else:
        form = CourseForm(instance=course)
    return render(request, "courses/instructor/course_form.html",
                  {"form": form, "mode": "edit", "course": course})


@instructor_required
def course_manage(request, slug):
    course = get_owned_course(request.user, slug)
    modules = (course.modules
               .prefetch_related("lessons__resources")
               .order_by("order", "id"))
    preview_token = make_preview_token(course) if not course.published else None
    return render(request, "courses/instructor/course_manage.html",
                  {"course": course, "modules": modules, "preview_token": preview_token})


@instructor_required
@require_POST
def course_delete(request, slug):
    course = get_owned_course(request.user, slug)
    # Don't let instructors nuke progress/certificates out from under learners.
    # Staff can still delete through the admin if they really need to.
    if Enrollment.objects.filter(course=course).exists():
        messages.error(
            request,
            "This course has enrolled learners — unpublish it instead of deleting.",
        )
        return redirect("courses:instructor_course_manage", slug=course.slug)
    course.delete()
    messages.success(request, "Course deleted.")
    return redirect("courses:instructor_dashboard")


# ---------- Module ----------

@instructor_required
def module_create(request, course_slug):
    course = get_owned_course(request.user, course_slug)
    if request.method == "POST":
        form = ModuleForm(request.POST)
        if form.is_valid():
            m = form.save(commit=False)
            m.course = course
            m.save()
            messages.success(request, "Module added.")
            return redirect("courses:instructor_course_manage", slug=course.slug)
    else:
        # Next default order = highest + 1.
        next_order = (course.modules.order_by("-order").values_list("order", flat=True).first() or 0) + 1
        form = ModuleForm(initial={"order": next_order})
    return render(request, "courses/instructor/module_form.html",
                  {"form": form, "course": course, "mode": "create"})


@instructor_required
def module_edit(request, course_slug, module_id):
    course, module = get_owned_module(request.user, course_slug, module_id)
    if request.method == "POST":
        form = ModuleForm(request.POST, instance=module)
        if form.is_valid():
            form.save()
            messages.success(request, "Module updated.")
            return redirect("courses:instructor_course_manage", slug=course.slug)
    else:
        form = ModuleForm(instance=module)
    return render(request, "courses/instructor/module_form.html",
                  {"form": form, "course": course, "module": module, "mode": "edit"})


@instructor_required
@require_POST
def module_delete(request, course_slug, module_id):
    course, module = get_owned_module(request.user, course_slug, module_id)
    module.delete()
    messages.success(request, "Module deleted.")
    return redirect("courses:instructor_course_manage", slug=course.slug)


# ---------- Lesson ----------

@instructor_required
def lesson_create(request, course_slug, module_id):
    course, module = get_owned_module(request.user, course_slug, module_id)
    if request.method == "POST":
        form = LessonForm(request.POST, request.FILES)
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.module = module
            lesson.save()
            messages.success(request, "Lesson added.")
            return redirect("courses:instructor_lesson_edit",
                            course_slug=course.slug, module_id=module.id, lesson_id=lesson.id)
    else:
        next_order = (module.lessons.order_by("-order").values_list("order", flat=True).first() or 0) + 1
        form = LessonForm(initial={"order": next_order})
    return render(request, "courses/instructor/lesson_form.html",
                  {"form": form, "course": course, "module": module, "mode": "create"})


@instructor_required
def lesson_edit(request, course_slug, module_id, lesson_id):
    course, module, lesson = get_owned_lesson(request.user, course_slug, module_id, lesson_id)
    if request.method == "POST":
        form = LessonForm(request.POST, request.FILES, instance=lesson)
        if form.is_valid():
            form.save()
            messages.success(request, "Lesson updated.")
            return redirect("courses:instructor_lesson_edit",
                            course_slug=course.slug, module_id=module.id, lesson_id=lesson.id)
    else:
        form = LessonForm(instance=lesson)
    resource_form = LessonResourceForm()
    return render(request, "courses/instructor/lesson_form.html", {
        "form": form, "course": course, "module": module, "lesson": lesson,
        "resource_form": resource_form, "mode": "edit",
    })


@instructor_required
@require_POST
def lesson_delete(request, course_slug, module_id, lesson_id):
    course, module, lesson = get_owned_lesson(request.user, course_slug, module_id, lesson_id)
    lesson.delete()
    messages.success(request, "Lesson deleted.")
    return redirect("courses:instructor_course_manage", slug=course.slug)


# ---------- Lesson resource (file attachments) ----------

@instructor_required
@require_POST
def resource_upload(request, course_slug, module_id, lesson_id):
    course, module, lesson = get_owned_lesson(request.user, course_slug, module_id, lesson_id)
    form = LessonResourceForm(request.POST, request.FILES)
    if form.is_valid():
        resource = form.save(commit=False)
        resource.lesson = lesson
        resource.save()
        messages.success(request, "Resource uploaded.")
    else:
        # Surface the first error so the author sees what to fix.
        first = next(iter(form.errors.values()), ["Upload failed."])[0]
        messages.error(request, f"Resource upload failed: {first}")
    return redirect("courses:instructor_lesson_edit",
                    course_slug=course.slug, module_id=module.id, lesson_id=lesson.id)


@instructor_required
@require_POST
def resource_delete(request, course_slug, module_id, lesson_id, resource_id):
    course, module, lesson, resource = get_owned_resource(
        request.user, course_slug, module_id, lesson_id, resource_id
    )
    resource.delete()
    messages.success(request, "Resource removed.")
    return redirect("courses:instructor_lesson_edit",
                    course_slug=course.slug, module_id=module.id, lesson_id=lesson.id)


# ---------- Quick publish toggle ----------

@instructor_required
@require_POST
def course_toggle_publish(request, slug):
    course = get_owned_course(request.user, slug)
    # A course that's never been approved must go through editorial review
    # before it can go live. After the first approval, the instructor can
    # unpublish/republish freely.
    if course.approved_at is None:
        if course.review_status == "pending":
            messages.info(request, "Course is already awaiting staff review.")
        else:
            course.review_status = "pending"
            course.submitted_at = timezone.now()
            course.save(update_fields=["review_status", "submitted_at"])
            messages.success(request, "Submitted for review — a staff member will take a look shortly.")
        return redirect("courses:instructor_course_manage", slug=course.slug)

    course.published = not course.published
    course.save(update_fields=["published"])
    messages.success(
        request,
        "Course is now live." if course.published else "Course unpublished.",
    )
    return redirect("courses:instructor_course_manage", slug=course.slug)


# ---------- Staff editorial review ----------

@staff_member_required
def review_queue(request):
    from apps.courses.models import Course as _Course
    pending = (_Course.objects.filter(review_status="pending")
               .select_related("instructor", "category")
               .order_by("submitted_at"))
    recent = (_Course.objects.exclude(review_status__in=["draft", "pending"])
              .select_related("instructor", "category")
              .order_by("-approved_at")[:10])
    return render(request, "courses/instructor/review_queue.html",
                  {"pending": pending, "recent": recent})


@staff_member_required
@require_POST
def review_approve(request, slug):
    from apps.courses.models import Course as _Course
    course = get_object_or_404(_Course, slug=slug)
    # Only pending courses can be acted on — prevents re-approving an already
    # approved course (which would bump `approved_at`) or approving a draft.
    if course.review_status != "pending":
        messages.error(request, "Only courses awaiting review can be approved.")
        return redirect("courses:review_queue")
    course.review_status = "approved"
    course.approved_at = course.approved_at or timezone.now()
    course.published = True
    course.review_notes = ""
    course.save(update_fields=["review_status", "approved_at", "published", "review_notes"])
    notify_course_review_decision(course, "approved")
    messages.success(request, f"Approved and published “{course.title}”.")
    return redirect("courses:review_queue")


@staff_member_required
@require_POST
def review_request_changes(request, slug):
    from apps.courses.models import Course as _Course
    course = get_object_or_404(_Course, slug=slug)
    if course.review_status != "pending":
        messages.error(request, "Only courses awaiting review can be sent back.")
        return redirect("courses:review_queue")
    notes = (request.POST.get("notes") or "").strip()
    course.review_status = "changes_requested"
    course.review_notes = notes or "Please revise and resubmit."
    course.published = False
    course.save(update_fields=["review_status", "review_notes", "published"])
    notify_course_review_decision(course, "changes_requested", notes=course.review_notes)
    messages.success(request, f"Changes requested on “{course.title}”.")
    return redirect("courses:review_queue")
