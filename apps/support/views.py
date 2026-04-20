import json

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.ratelimit import rate_limit

from .bot import generate_reply
from .models import SupportMessage, SupportThread


def _get_or_create_thread(request):
    """Resolve the active support thread for this user/session, creating if needed.

    Security: when an authenticated user arrives, ignore session_key entirely —
    threads are scoped strictly by `user`. Anonymous threads are keyed by
    session_key, and once the session's owner logs in we claim any anon thread
    that shared this session_key so the handoff is seamless, but from that
    point on the thread is bound to `user`.
    """
    if not request.session.session_key:
        request.session.save()
    skey = request.session.session_key

    if request.user.is_authenticated:
        # Claim any anon thread riding this session so mid-chat login works.
        SupportThread.objects.filter(
            user__isnull=True, session_key=skey,
        ).update(user=request.user)
        thread = (SupportThread.objects
                  .exclude(status="resolved")
                  .filter(user=request.user)
                  .first())
        if thread:
            return thread
        return SupportThread.objects.create(
            user=request.user, session_key=skey, subject="Support chat",
        )

    thread = (SupportThread.objects
              .exclude(status="resolved")
              .filter(user__isnull=True, session_key=skey)
              .first())
    if thread:
        return thread
    return SupportThread.objects.create(
        user=None, session_key=skey, subject="Support chat",
    )


def widget_page(request):
    """Standalone full-page view of the chat — linked from dashboard, contact, etc."""
    thread = _get_or_create_thread(request)
    return render(request, "support/chat.html", {"thread": thread})


@require_POST
@rate_limit(key="support_send", max_hits=20, window_seconds=60)
def api_send(request):
    """AJAX endpoint: user posts a message, bot (or agent) replies.

    Payload: {"body": "..."} (JSON or form-encoded).
    Response: {"messages": [{role, body, created_at}, ...], "status": thread.status}
    """
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Bad JSON")
    else:
        data = request.POST
    body = (data.get("body") or "").strip()
    if not body:
        return HttpResponseBadRequest("Empty message")

    thread = _get_or_create_thread(request)
    thread.updated_at = timezone.now()
    thread.save(update_fields=["updated_at"])

    user_msg = SupportMessage.objects.create(
        thread=thread, role="user",
        author=request.user if request.user.is_authenticated else None,
        body=body,
    )

    # If a human is handling the thread, don't let the bot interrupt.
    bot_msg = None
    if thread.status in {"bot"}:
        reply = generate_reply(body)
        bot_msg = SupportMessage.objects.create(
            thread=thread, role="bot", body=reply.text,
        )
        if reply.escalate:
            thread.status = "awaiting_agent"
            thread.save(update_fields=["status"])
    elif thread.status == "awaiting_agent":
        SupportMessage.objects.create(
            thread=thread, role="system",
            body="A human agent will reply shortly. You can keep typing — they'll see everything.",
        )

    def serialize(m):
        return {
            "id": m.id, "role": m.role, "body": m.body,
            "created_at": m.created_at.isoformat(),
        }

    msgs = [serialize(user_msg)]
    if bot_msg:
        msgs.append(serialize(bot_msg))
    # Also include any system/agent messages created since user_msg (for awaiting_agent path).
    tail = thread.messages.filter(id__gt=user_msg.id).exclude(id=bot_msg.id if bot_msg else 0)
    for m in tail:
        msgs.append(serialize(m))

    return JsonResponse({"status": thread.status, "messages": msgs})


def api_poll(request):
    """Return the current thread transcript — used for agent replies arriving async."""
    thread = _get_or_create_thread(request)
    data = [
        {"id": m.id, "role": m.role, "body": m.body, "created_at": m.created_at.isoformat()}
        for m in thread.messages.all()
    ]
    return JsonResponse({"status": thread.status, "messages": data})


# --- Staff (human agent) views ------------------------------------------

@staff_member_required
def thread_list(request):
    threads = SupportThread.objects.all().select_related("user", "assigned_agent")
    status = request.GET.get("status")
    if status:
        threads = threads.filter(status=status)
    return render(request, "support/thread_list.html",
                  {"threads": threads, "active_status": status})


@staff_member_required
def thread_detail(request, thread_id):
    thread = get_object_or_404(SupportThread, id=thread_id)
    if request.method == "POST":
        body = (request.POST.get("body") or "").strip()
        action = request.POST.get("action")
        if action == "claim":
            thread.assigned_agent = request.user
            thread.status = "with_agent"
            thread.save()
            SupportMessage.objects.create(
                thread=thread, role="system",
                body=f"{request.user.get_full_name() or request.user.username} joined the chat.",
            )
        elif action == "resolve":
            thread.status = "resolved"
            thread.save()
            SupportMessage.objects.create(
                thread=thread, role="system", body="Thread marked as resolved.",
            )
        elif body:
            SupportMessage.objects.create(
                thread=thread, role="agent", author=request.user, body=body,
            )
            if thread.status in {"bot", "awaiting_agent"}:
                thread.status = "with_agent"
                thread.assigned_agent = thread.assigned_agent or request.user
                thread.save()
        return redirect("support:thread_detail", thread_id=thread.id)
    return render(request, "support/thread_detail.html", {"thread": thread})
