"""Permission helpers for the instructor workspace."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.text import slugify


PREVIEW_SALT = "courses.preview"
PREVIEW_MAX_AGE_SECONDS = 60 * 60 * 24 * 14  # 14 days


def make_preview_token(course):
    """Sign a token that lets anyone who has the link view an unpublished course."""
    return TimestampSigner(salt=PREVIEW_SALT).sign(str(course.pk))


def valid_preview_token(course, token):
    if not token:
        return False
    try:
        value = TimestampSigner(salt=PREVIEW_SALT).unsign(
            token, max_age=PREVIEW_MAX_AGE_SECONDS
        )
    except (BadSignature, SignatureExpired):
        return False
    return value == str(course.pk)

from apps.accounts.models import Profile
from apps.courses.models import Course, Instructor, Lesson, LessonResource, Module


def ensure_instructor_for(user):
    """
    Get or create the Instructor row tied to this platform user.

    We auto-create the row the first time an instructor-role user enters
    the workspace, so there's zero setup friction. Staff can always author.
    """
    instructor = Instructor.objects.filter(user=user).first()
    if instructor:
        return instructor
    base_name = user.get_full_name() or user.username
    slug = slugify(base_name) or f"user-{user.pk}"
    # Collision-safe slug (Instructor.slug is unique).
    suffix, slug_try = 0, slug
    while Instructor.objects.filter(slug=slug_try).exists():
        suffix += 1
        slug_try = f"{slug}-{suffix}"
    return Instructor.objects.create(user=user, name=base_name, slug=slug_try)


def _can_author(user):
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    profile = Profile.objects.filter(user=user).first()
    return bool(profile and profile.role == "instructor")


def instructor_required(view):
    """Gate a view to users who can author courses (instructor role or staff)."""
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not _can_author(request.user):
            return redirect("courses:instructor_denied")
        return view(request, *args, **kwargs)
    return wrapper


# ---- Ownership lookups -------------------------------------------------------

def _owned_course_qs(user):
    qs = Course.objects.all()
    if user.is_staff:
        return qs
    return qs.filter(instructor__user=user)


def get_owned_course(user, slug):
    try:
        return _owned_course_qs(user).get(slug=slug)
    except Course.DoesNotExist as e:
        raise Http404("Course not found or not yours.") from e


def get_owned_module(user, course_slug, module_id):
    course = get_owned_course(user, course_slug)
    return course, get_object_or_404(Module, pk=module_id, course=course)


def get_owned_lesson(user, course_slug, module_id, lesson_id):
    course, module = get_owned_module(user, course_slug, module_id)
    lesson = get_object_or_404(Lesson, pk=lesson_id, module=module)
    return course, module, lesson


def get_owned_resource(user, course_slug, module_id, lesson_id, resource_id):
    course, module, lesson = get_owned_lesson(user, course_slug, module_id, lesson_id)
    resource = get_object_or_404(LessonResource, pk=resource_id, lesson=lesson)
    return course, module, lesson, resource
