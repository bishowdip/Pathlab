# EdTech SaaS — Django

A Yandex Practicum–inspired EdTech platform for **Nepal (entrance exams) + global (kids' AI/Python camp)**.

Three pillars:

1. **Entrance Prep** (subscription-based MCQ) — CMAT · BSc CSIT · BIT · BCA · BBA · **IELTS · PTE**
2. **Tech Upskilling** (course-based) — SQL · Data Analysis · Data Science
3. **Kids' Summer Camp** (seasonal) — Scratch · Python · AI for kids

## Stack

- Django 5 + Tailwind CSS (via CDN — swap for a build step later)
- SQLite for dev · PostgreSQL-ready for prod
- Built-in Django auth · `UserCreationForm` for signup
- **Payments stubbed** for eSewa, Khalti, Stripe — wire real keys in `settings.PAYMENT_GATEWAYS`

## Quickstart

```bash
cd /Users/bishowdip/EdTech
source .venv/bin/activate         # venv already created
python manage.py migrate
python manage.py seed_demo        # categories, courses, exams (CMAT/IELTS/PTE...), plans
python manage.py createsuperuser  # for /admin/
python manage.py runserver
```

Visit:
- `/`                — homepage (7-section Yandex-style layout)
- `/courses/`        — course catalog with pillar filters
- `/exams/`          — mock exams (CMAT, IELTS, PTE, CSIT, BBA, BIT)
- `/subscriptions/`  — pricing plans
- `/accounts/signup/` → sign up → take a free exam (`/exams/cmat-quant-drill/`)
- `/admin/`          — full CMS for courses, exams, questions, plans, site settings

## Project layout

```
edtech_platform/        # Django project settings + root urls
apps/
  core/                 # homepage, site settings, trust signals, seed command
  accounts/             # signup, login, dashboard, Profile model
  courses/              # Category / Course / Testimonial / SuccessStat
  exams/                # Exam / Question / Choice / ExamAttempt / Answer
  subscriptions/        # Plan / Subscription / Payment + gateway stubs
                        # + SubscriptionAccessMiddleware (guards /exams/take/…)
templates/
  base.html             # shared shell (header, promo band, footer)
  _components/          # reusable course_card + exam_card
  core/                 # home.html (7 sections), about.html
  courses/  exams/  accounts/  subscriptions/
```

## MCQ engine — how it works

1. `/exams/<slug>/` → exam detail page (shows duration, questions, pass %)
2. `POST /exams/<slug>/start/` → creates an `ExamAttempt`, redirects to taking page
3. `/exams/take/<attempt_id>/` → client-side JS timer, no reload while navigating questions
4. `POST submit/` → scores server-side; answers & explanations are **only revealed after submit**
5. `/exams/result/<attempt_id>/` → per-question review with explanations

The `SubscriptionAccessMiddleware` + view-level check together enforce subscription gating: `is_free_preview=True` exams bypass it.

## Payments (stubbed)

All three gateways go through the same flow:

`/subscriptions/` → pricing → `/subscriptions/checkout/<plan-slug>/` → pick gateway → stub confirm page → `Subscription.activate()` → dashboard

To wire real keys, edit:
```python
# edtech_platform/settings.py
PAYMENT_GATEWAYS = {
    "esewa":  {"merchant_id": "...", ...},
    "khalti": {"public_key": "...", "secret_key": "..."},
    "stripe": {"public_key": "...", "secret_key": "..."},
}
```
Then replace the `*_init` views in `apps/subscriptions/views.py` with real gateway calls (eSewa form POST, Khalti `/epayment/initiate/`, Stripe Checkout Session).

## Design system (Yandex "puzzle" logic)

- Accent colors: `entrance-*` (green), `tech-*` (blue), `kids-*` (magenta/neon)
- Shapes: `shape-circle`, `shape-square`, `shape-triangle`, `shape-hexagon` (CSS clip-path)
- Cards: `templates/_components/course_card.html` & `exam_card.html` — drop in anywhere

## What's next (post-MVP)

- Move Tailwind from CDN → `django-tailwind` build (PageSpeed 90+)
- Switch SQLite → Postgres for prod
- Real Stripe Checkout + eSewa/Khalti integrations
- WhiteNoise + S3/R2 for media in production
- Kids' simplified dashboard (big buttons, progress badges)
- Seed more MCQs (currently 3–5 per exam — enough to smoke-test the engine)
