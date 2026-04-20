"""
Rule-based chatbot brain. Pluggable: swap `generate_reply` for an LLM call
(OpenAI / Anthropic) later without touching views.

The bot handles FAQs. When it can't answer confidently it returns
ESCALATE so the view flips the thread to `awaiting_agent`.
"""
from dataclasses import dataclass

ESCALATE = "__ESCALATE__"


@dataclass
class BotReply:
    text: str
    escalate: bool = False


# Each rule: (list_of_keywords, reply_text). First keyword match wins.
_RULES = [
    (["price", "pricing", "cost", "how much", "fee", "fees"],
     "Our plans start at NPR 499/month. You can compare all tiers on the Pricing page — "
     "local payments work via eSewa & Khalti, international via Stripe & PayPal."),
    (["refund", "money back", "cancel"],
     "You can cancel anytime from Dashboard → Subscriptions. "
     "We offer a 7-day refund on new subscriptions — reply with your order ID and I'll escalate to a human."),
    (["pdf", "download", "resource", "materials", "notes"],
     "Lesson resources (PDFs, slides) are on each lesson page under 'Resources'. "
     "Free-preview resources are open to everyone; the rest unlock with any active subscription."),
    (["video", "not playing", "buffering", "can't watch"],
     "Try refreshing, then check your connection. If a specific lesson video won't load, "
     "send me the course and lesson name and I'll loop in a human agent."),
    (["exam", "mock", "test", "practice"],
     "Mock exams live under /exams/. Each one is timed and scored instantly with explanations shown after you submit."),
    (["enroll", "how to start", "begin", "how do i start"],
     "Open any course, click 'Enroll & start' — you'll land on the first lesson. "
     "Paid courses require an active subscription; free courses start instantly."),
    (["kid", "child", "summer camp"],
     "Kids' Summer Camp is a dedicated pillar with a kid-friendly dashboard, badges, and video-first lessons. "
     "Browse /courses/?pillar=kids."),
    (["reset", "forgot password", "can't log in", "cant login"],
     "Reset your password at /accounts/password/reset/ — we'll email you a secure link."),
    (["hello", "hi", "hey", "namaste"],
     "Hi! 👋 I'm the PathLab assistant. Ask me about courses, pricing, payments, or exams — "
     "or type 'agent' to talk to a human."),
    (["agent", "human", "support", "talk to someone", "representative"],
     ESCALATE),
    (["thank", "thanks", "dhanyabad"],
     "You're welcome! Anything else I can help with?"),
]


def generate_reply(user_text: str) -> BotReply:
    """Rule-based reply. Returns BotReply with escalate=True to flag a human handoff."""
    text = (user_text or "").lower().strip()
    if not text:
        return BotReply("Type a question and I'll do my best to help.")

    for keywords, reply in _RULES:
        if any(k in text for k in keywords):
            if reply == ESCALATE:
                return BotReply(
                    "Got it — connecting you to a human agent. "
                    "They'll reply here as soon as they're free (usually within a few hours during Sun–Fri, 10am–6pm).",
                    escalate=True,
                )
            return BotReply(reply)

    # Unknown — offer escalation path but don't auto-escalate.
    return BotReply(
        "I'm not sure about that one. You can rephrase, or type 'agent' to reach a human on our team."
    )
