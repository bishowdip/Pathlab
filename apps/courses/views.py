from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.ratelimit import rate_limit

from .models import (
    Category, Course, CourseReview, Enrollment, Instructor, Lesson,
    LessonNote, LessonProgress, LessonResource, Module,
)
from .services import notify_course_completion, notify_enrollment


def _user_can_access(user, course, lesson=None, resource=None):
    """Gate helper: free course OR free-preview lesson/resource OR active subscription OR staff."""
    if user.is_staff:
        return True
    if course.is_free:
        return True
    if resource is not None and resource.is_free_preview:
        return True
    if lesson is not None and lesson.is_free_preview:
        return True
    if user.is_authenticated and user.subscriptions.filter(status="active").exists():
        return True
    return False


def course_list(request):
    pillar = request.GET.get("pillar")
    q = request.GET.get("q", "").strip()
    qs = Course.objects.filter(published=True).select_related("category")
    if pillar:
        qs = qs.filter(category__pillar=pillar)
    if q:
        qs = qs.filter(title__icontains=q)
    return render(
        request,
        "courses/list.html",
        {"courses": qs, "categories": Category.objects.all(),
         "active_pillar": pillar, "q": q},
    )


def course_detail(request, slug):
    course = get_object_or_404(
        Course.objects.prefetch_related("modules__lessons").select_related("instructor"),
        slug=slug,
    )
    # Unpublished courses are only visible to: (a) staff, (b) the owning instructor,
    # (c) anyone with a valid signed preview token.
    if not course.published:
        from apps.courses.instructor.permissions import valid_preview_token
        is_owner = (request.user.is_authenticated and
                    (request.user.is_staff or
                     (course.instructor_id and course.instructor.user_id == request.user.id)))
        if not (is_owner or valid_preview_token(course, request.GET.get("preview"))):
            raise Http404()
    enrollment = my_review = None
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(user=request.user, course=course).first()
        my_review = CourseReview.objects.filter(user=request.user, course=course).first()
    reviews = course.reviews.select_related("user")[:10]
    return render(
        request,
        "courses/detail.html",
        {
            "course": course, "enrollment": enrollment,
            "reviews": reviews, "my_review": my_review,
            "can_review": bool(enrollment),
        },
    )


@login_required
@require_POST
def enroll(request, slug):
    course = get_object_or_404(Course, slug=slug, published=True)
    if not course.is_free and not request.user.is_staff:
        has_active = request.user.subscriptions.filter(status="active").exists()
        if not has_active:
            messages.info(request, f"Subscribe to unlock {course.title}.")
            return redirect("subscriptions:pricing")
    enrollment, created = Enrollment.objects.get_or_create(
        user=request.user, course=course
    )
    if created:
        messages.success(request, f"Enrolled in {course.title} — let's go!")
        notify_enrollment(enrollment)
    first_lesson = Lesson.objects.filter(module__course=course).order_by("module__order", "order").first()
    if first_lesson:
        return redirect(
            "courses:lesson",
            course_slug=course.slug,
            module_id=first_lesson.module_id,
            lesson_slug=first_lesson.slug,
        )
    return redirect(course.get_absolute_url())


@login_required
def lesson_view(request, course_slug, module_id, lesson_slug):
    course = get_object_or_404(Course, slug=course_slug, published=True)
    module = get_object_or_404(Module, id=module_id, course=course)
    lesson = get_object_or_404(Lesson, module=module, slug=lesson_slug)

    # Enforce subscription unless the lesson is a free preview
    if not lesson.is_free_preview and not request.user.is_staff:
        has_active = request.user.subscriptions.filter(status="active").exists()
        if not has_active:
            messages.info(request, "This lesson requires an active subscription.")
            return redirect("subscriptions:pricing")

    enrollment, _ = Enrollment.objects.get_or_create(user=request.user, course=course)
    progress, _ = LessonProgress.objects.get_or_create(
        enrollment=enrollment, lesson=lesson
    )

    lessons_qs = Lesson.objects.filter(module__course=course).order_by(
        "module__order", "order"
    )
    lesson_list = list(lessons_qs)
    try:
        idx = next(i for i, l in enumerate(lesson_list) if l.id == lesson.id)
    except StopIteration:
        raise Http404
    prev_lesson = lesson_list[idx - 1] if idx > 0 else None
    next_lesson = lesson_list[idx + 1] if idx + 1 < len(lesson_list) else None

    profile = getattr(request.user, "profile", None)
    is_kid = bool(profile and profile.role == "kid")
    note = LessonNote.objects.filter(user=request.user, lesson=lesson).first()

    return render(
        request,
        "courses/lesson.html",
        {
            "course": course, "module": module, "lesson": lesson,
            "enrollment": enrollment, "progress": progress,
            "prev_lesson": prev_lesson, "next_lesson": next_lesson,
            "modules": course.modules.prefetch_related("lessons"),
            "is_kid": is_kid,
            "note": note,
        },
    )


@login_required
@require_POST
def mark_lesson_complete(request, course_slug, module_id, lesson_slug):
    course = get_object_or_404(Course, slug=course_slug, published=True)
    lesson = get_object_or_404(Lesson, module__course=course, module_id=module_id, slug=lesson_slug)
    enrollment, _ = Enrollment.objects.get_or_create(user=request.user, course=course)
    progress, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=lesson)
    if not progress.completed:
        progress.completed = True
        progress.completed_at = timezone.now()
        progress.save()

    # Auto-award course completion badge + close out enrollment.
    if enrollment.progress_percent == 100 and not enrollment.completed_at:
        enrollment.completed_at = timezone.now()
        enrollment.save()
        _award_completion_badge(request.user, course)
        notify_course_completion(enrollment)

    lessons_qs = Lesson.objects.filter(module__course=course).order_by("module__order", "order")
    lessons = list(lessons_qs)
    idx = next((i for i, l in enumerate(lessons) if l.id == lesson.id), None)
    nxt = lessons[idx + 1] if idx is not None and idx + 1 < len(lessons) else None
    if nxt:
        return redirect(
            "courses:lesson",
            course_slug=course.slug, module_id=nxt.module_id, lesson_slug=nxt.slug,
        )
    messages.success(request, f"🎉 You finished {course.title}!")
    return redirect(course.get_absolute_url())


@login_required
def lesson_video(request, course_slug, module_id, lesson_slug):
    """Streams an uploaded lesson video, gated by access rules."""
    course = get_object_or_404(Course, slug=course_slug, published=True)
    lesson = get_object_or_404(
        Lesson, module__course=course, module_id=module_id, slug=lesson_slug
    )
    if not lesson.video_file:
        raise Http404
    if not _user_can_access(request.user, course, lesson=lesson):
        messages.info(request, "Subscribe to watch this lesson.")
        return redirect("subscriptions:pricing")
    return FileResponse(lesson.video_file.open("rb"), content_type="video/mp4")


@login_required
def resource_download(request, resource_id):
    """Serves a LessonResource file only if the user has access to its course."""
    resource = get_object_or_404(
        LessonResource.objects.select_related("lesson__module__course"),
        id=resource_id,
    )
    course = resource.lesson.module.course
    if not _user_can_access(request.user, course, lesson=resource.lesson, resource=resource):
        messages.info(request, "Subscribe to download this resource.")
        return redirect("subscriptions:pricing")
    # FileResponse streams the file with the right headers; as_attachment forces download.
    # Sanitize the filename — strip any CR/LF/directory chars so a malicious
    # storage key can't inject headers via Content-Disposition.
    raw_name = resource.file.name.rsplit("/", 1)[-1]
    safe_name = "".join(c for c in raw_name if c not in "\r\n\"\\") or "download"
    response = FileResponse(resource.file.open("rb"), as_attachment=True,
                            filename=safe_name)
    return response


# --- Reviews -----------------------------------------------------------

@login_required
@require_POST
@rate_limit(key="post_review", max_hits=10, window_seconds=600)
def post_review(request, slug):
    course = get_object_or_404(Course, slug=slug, published=True)
    # Only learners who enrolled can review.
    if not Enrollment.objects.filter(user=request.user, course=course).exists():
        messages.error(request, "Enroll first, then leave a review.")
        return redirect(course.get_absolute_url())
    try:
        rating = max(1, min(5, int(request.POST.get("rating", 5))))
    except (TypeError, ValueError):
        rating = 5
    body = (request.POST.get("body") or "").strip()
    CourseReview.objects.update_or_create(
        user=request.user, course=course,
        defaults={"rating": rating, "body": body},
    )
    messages.success(request, "Thanks for the review!")
    return redirect(course.get_absolute_url() + "#reviews")


# --- Lesson notes ------------------------------------------------------

@login_required
@require_POST
def save_note(request, course_slug, module_id, lesson_slug):
    lesson = get_object_or_404(
        Lesson, module__course__slug=course_slug,
        module_id=module_id, slug=lesson_slug,
    )
    body = (request.POST.get("body") or "").strip()
    if body:
        LessonNote.objects.update_or_create(
            user=request.user, lesson=lesson, defaults={"body": body},
        )
        messages.success(request, "Note saved.")
    else:
        LessonNote.objects.filter(user=request.user, lesson=lesson).delete()
        messages.info(request, "Note cleared.")
    return redirect("courses:lesson",
                    course_slug=course_slug, module_id=module_id, lesson_slug=lesson_slug)


# --- Certificate -------------------------------------------------------

@login_required
def certificate(request, slug):
    course = get_object_or_404(Course, slug=slug, published=True)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)
    if enrollment.progress_percent < 100 and not request.user.is_staff:
        messages.info(request, "Finish every lesson to unlock your certificate.")
        return redirect(course.get_absolute_url())
    return render(request, "courses/certificate.html",
                  {"course": course, "enrollment": enrollment})


@login_required
def certificate_pdf(request, slug):
    """Download the same certificate as a PDF."""
    from django.http import HttpResponse
    from .pdf import render_certificate_pdf

    course = get_object_or_404(Course, slug=slug, published=True)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)
    if enrollment.progress_percent < 100 and not request.user.is_staff:
        raise Http404()
    student = request.user.get_full_name() or request.user.username
    completed = enrollment.completed_at.date() if enrollment.completed_at else None
    pdf = render_certificate_pdf(
        student_name=student, course_title=course.title,
        completed_on=completed,
        reference=f"C-{course.id}-{enrollment.id}",
    )
    response = HttpResponse(pdf, content_type="application/pdf")
    filename = f"certificate-{course.slug}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# --- Instructor --------------------------------------------------------

def instructor_detail(request, slug):
    instructor = get_object_or_404(Instructor, slug=slug)
    courses = instructor.courses.filter(published=True)
    return render(request, "courses/instructor_detail.html",
                  {"instructor": instructor, "courses": courses})


def _award_completion_badge(user, course):
    from .models import Badge, UserBadge

    badge, _ = Badge.objects.get_or_create(
        slug=f"completed-{course.slug}",
        defaults={
            "name": f"Completed: {course.title}",
            "description": f"Finished every lesson in {course.title}.",
            "icon_shape": course.category.shape,
            "color": course.category.accent_color,
        },
    )
    UserBadge.objects.get_or_create(user=user, badge=badge)
