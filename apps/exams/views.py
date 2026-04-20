from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Answer, Choice, Exam, ExamAttempt


def exam_list(request):
    q = request.GET.get("q", "").strip()
    exams = Exam.objects.filter(published=True)
    if q:
        exams = exams.filter(name__icontains=q)
    grouped = OrderedDict()
    for exam in exams:
        grouped.setdefault(exam.get_exam_type_display(), []).append(exam)
    return render(request, "exams/list.html", {"grouped": grouped, "q": q})


def exam_detail(request, slug):
    exam = get_object_or_404(Exam, slug=slug, published=True)
    user_attempts = []
    if request.user.is_authenticated:
        user_attempts = request.user.attempts.filter(exam=exam)[:5]
    top_scores = (
        ExamAttempt.objects.filter(exam=exam, status="submitted")
        .order_by("-score")[:5]
    )
    return render(
        request, "exams/detail.html",
        {"exam": exam, "user_attempts": user_attempts, "top_scores": top_scores},
    )


@login_required
def start_attempt(request, slug):
    exam = get_object_or_404(Exam, slug=slug, published=True)
    if exam.requires_subscription and not exam.is_free_preview and not request.user.is_staff:
        active_subs = request.user.subscriptions.filter(status="active")
        # Plan-scoped exams (e.g. cmat-pro unlocks the CMAT exam) require a
        # matching active subscription — a generic Tech plan shouldn't unlock CMAT.
        if exam.required_plan_slug:
            active_subs = active_subs.filter(plan__slug=exam.required_plan_slug)
        if not active_subs.exists():
            messages.info(request, f"Subscribe to unlock {exam.name}.")
            return redirect("subscriptions:pricing")

    # Resume an in-progress attempt instead of spawning duplicates; if it has
    # already run past the deadline, score it as expired and show the result.
    existing = ExamAttempt.objects.filter(
        user=request.user, exam=exam, status="in_progress"
    ).first()
    if existing:
        if existing.time_remaining_seconds <= 0:
            _score_attempt(existing, expired=True)
            return redirect("exams:result", attempt_id=existing.id)
        return redirect("exams:take", attempt_id=existing.id)

    attempt = ExamAttempt.objects.create(
        user=request.user, exam=exam, total=exam.questions.count()
    )
    return redirect("exams:take", attempt_id=attempt.id)


@login_required
def take_exam(request, attempt_id):
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, user=request.user)
    if attempt.status != "in_progress":
        return redirect("exams:result", attempt_id=attempt.id)
    if attempt.time_remaining_seconds <= 0:
        _score_attempt(attempt, expired=True)
        return redirect("exams:result", attempt_id=attempt.id)

    questions = list(attempt.exam.questions.prefetch_related("choices"))
    sections = OrderedDict()
    for q in questions:
        sections.setdefault(q.section or "General", []).append(q)

    return render(
        request,
        "exams/take.html",
        {
            "attempt": attempt, "exam": attempt.exam,
            "questions": questions, "sections": sections,
            "time_remaining": attempt.time_remaining_seconds,
        },
    )


@login_required
@require_POST
def submit_attempt(request, attempt_id):
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, user=request.user)
    if attempt.status != "in_progress":
        return redirect("exams:result", attempt_id=attempt.id)

    # Late submission — score whatever answers arrived, flag as expired so
    # the UI can show "timed out" rather than a clean submission.
    expired = attempt.time_remaining_seconds <= 0

    for question in attempt.exam.questions.all():
        choice_id = request.POST.get(f"question_{question.id}")
        selected = None
        is_correct = False
        if choice_id:
            try:
                selected = Choice.objects.get(id=choice_id, question=question)
                is_correct = selected.is_correct
            except Choice.DoesNotExist:
                selected = None
        Answer.objects.update_or_create(
            attempt=attempt, question=question,
            defaults={"selected_choice": selected, "is_correct": is_correct},
        )
    _score_attempt(attempt, expired=expired)
    return redirect("exams:result", attempt_id=attempt.id)


def _score_attempt(attempt, expired=False):
    attempt.score = attempt.answers.filter(is_correct=True).count()
    attempt.total = attempt.exam.questions.count()
    attempt.submitted_at = timezone.now()
    attempt.status = "expired" if expired else "submitted"
    attempt.save()


@login_required
def result(request, attempt_id):
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("exam"),
        id=attempt_id, user=request.user,
    )
    answers = (
        attempt.answers
        .select_related("question", "selected_choice")
        .prefetch_related("question__choices")
    )

    # Section-wise breakdown
    section_breakdown = OrderedDict()
    for a in answers:
        key = a.question.section or "General"
        sb = section_breakdown.setdefault(key, {"correct": 0, "total": 0})
        sb["total"] += 1
        if a.is_correct:
            sb["correct"] += 1
    for k, v in section_breakdown.items():
        v["percent"] = round(v["correct"] / v["total"] * 100, 1) if v["total"] else 0

    return render(
        request,
        "exams/result.html",
        {"attempt": attempt, "answers": answers, "section_breakdown": section_breakdown},
    )


def leaderboard(request, slug):
    exam = get_object_or_404(Exam, slug=slug, published=True)
    top = (
        ExamAttempt.objects
        .filter(exam=exam, status="submitted")
        .values("user__username")
        .annotate(best=Max("score"), attempts=Count("id"))
        .order_by("-best")[:25]
    )
    stats = ExamAttempt.objects.filter(exam=exam, status="submitted").aggregate(
        avg=Avg("score"), attempts=Count("id")
    )
    return render(
        request, "exams/leaderboard.html",
        {"exam": exam, "top": top, "stats": stats},
    )
