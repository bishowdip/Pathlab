from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render

from apps.core.analytics import collect as collect_analytics
from apps.core.ratelimit import rate_limit

from apps.courses.models import Category, Course, Instructor, SuccessStat, Testimonial
from apps.core.models import TrustSignal
from apps.exams.models import Exam
from apps.subscriptions.models import Plan


def home(request):
    pillar = request.GET.get("pillar", "all")

    courses_qs = Course.objects.filter(published=True).select_related("category")
    entrance_courses = courses_qs.filter(category__pillar="entrance")[:6]
    tech_courses = courses_qs.filter(category__pillar="tech")[:6]
    kids_courses = courses_qs.filter(category__pillar="kids")[:6]

    if pillar == "entrance":
        main_catalog = entrance_courses
    elif pillar == "tech":
        main_catalog = tech_courses
    elif pillar == "kids":
        main_catalog = kids_courses
    else:
        main_catalog = list(entrance_courses) + list(tech_courses)

    context = {
        "pillar": pillar,
        "categories": Category.objects.all(),
        "main_catalog": main_catalog,
        "kids_courses": kids_courses,
        "featured_testimonials": Testimonial.objects.filter(is_featured=True)[:3],
        "video_testimonials": Testimonial.objects.filter(is_video=True)[:5],
        "success_stats": SuccessStat.objects.all(),
        "trust_signals": TrustSignal.objects.all(),
        "featured_exams": Exam.objects.filter(published=True)[:6],
        "plans": Plan.objects.filter(is_active=True),
    }
    return render(request, "core/home.html", context)


def about(request):
    # Hard-coded because the team is small and static — no admin UI needed.
    # When it grows past ~10 people, lift this into a TeamMember model.
    leadership = [
        {"name": "Bishowdip Thapa", "role": "Team Lead",
         "initials": "BT", "bg": "bg-entrance-600",
         "photo": "img/team/BishowdipThapa.jpeg"},
        {"name": "Abhishek Tiwari", "role": "Project Manager",
         "initials": "AT", "bg": "bg-tech-600",
         "photo": "img/team/AbhishekTiwari.png"},
    ]
    developers = [
        {"name": "Manjil Basnet",   "initials": "MB", "bg": "bg-entrance-500",
         "photo": "img/team/ManjilBasnet.png"},
        {"name": "Abhi Khatiwada",  "initials": "AK", "bg": "bg-tech-500",
         "photo": "img/team/AbhishekKhatiwada.png"},
        {"name": "Aryan Shrestha",  "initials": "AS", "bg": "bg-kids-500",
         "photo": "img/team/AryanShrestha.jpeg"},
        {"name": "Md Arbaz Rain",   "initials": "MA", "bg": "bg-entrance-700",
         "photo": "img/team/ArbazRain.jpeg"},
    ]
    return render(request, "core/about.html",
                  {"leadership": leadership, "developers": developers})


def search(request):
    """Global search across courses, exams, and instructors."""
    from apps.exams.models import Exam
    q = (request.GET.get("q") or "").strip()
    courses = exams = instructors = []
    if q:
        courses = Course.objects.filter(published=True, title__icontains=q)[:20]
        exams = Exam.objects.filter(published=True, name__icontains=q)[:20]
        instructors = Instructor.objects.filter(name__icontains=q)[:20]
    return render(request, "core/search.html",
                  {"q": q, "courses": courses, "exams": exams, "instructors": instructors})


def terms(request):
    return render(request, "core/terms.html")


def privacy(request):
    return render(request, "core/privacy.html")


@staff_member_required
def staff_dashboard(request):
    return render(request, "core/staff_dashboard.html", collect_analytics())


def instructors_directory(request):
    instructors = Instructor.objects.all()
    return render(request, "core/instructors.html", {"instructors": instructors})


@rate_limit(key="contact", max_hits=5, window_seconds=600)
def contact(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        message_body = (request.POST.get("message") or "").strip()
        if not (name and email and message_body):
            messages.error(request, "Please fill in every field — we read each one.")
            return redirect("core:contact")
        # TODO: persist to DB or send via email backend. For MVP, log + flash.
        import logging
        logging.getLogger(__name__).info(
            "Contact form: name=%s email=%s message=%s", name, email, message_body
        )
        messages.success(
            request, f"Thanks {name} — we'll get back to you at {email} within 24 hours."
        )
        return redirect("core:contact")
    return render(request, "core/contact.html")
