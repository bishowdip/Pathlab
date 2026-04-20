from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import SiteSettings, TrustSignal
from apps.courses.models import (
    Badge, Category, Course, Lesson, Module, SuccessStat, Testimonial,
)
from apps.exams.models import Choice, Exam, Question
from apps.subscriptions.models import Plan


COURSES = [
    # Entrance (green)
    {"cat": "CMAT", "title": "CMAT Full Prep", "tag": "Quant + Verbal + Logic, with 2000+ MCQs.",
     "desc": "Complete CMAT coverage with weekly mocks, topic diagnostics, and full solutions.",
     "difficulty": "scratch", "price": 3999, "featured": True,
     "testimonial": ("Rohit K.", "CMAT 2025 top 5%", "Passed CMAT on first attempt. The timed mocks were a lifesaver.")},
    {"cat": "BSc CSIT", "title": "BSc CSIT Entrance", "tag": "TU entrance · Physics · Math · English · CS.",
     "desc": "TU BSc CSIT entrance — curriculum-aligned with topic drills and two full mocks.",
     "difficulty": "scratch", "price": 2999,
     "testimonial": ("Aayushma S.", "CSIT 2024 qualifier", "Clean UI. Way better than the PDF-book combo I was doing before.")},
    {"cat": "IELTS", "title": "IELTS Academic 7.0+", "tag": "Listening · Reading · Writing · Speaking.",
     "desc": "Structured IELTS Academic prep — band 7+ focus, with writing feedback and mock tests.",
     "difficulty": "experienced", "price": 5499, "featured": True,
     "testimonial": ("Sita P.", "IELTS 7.5 overall", "Went from 6.0 to 7.5 in 8 weeks.")},
    {"cat": "PTE", "title": "PTE Academic Accelerator", "tag": "AI-scored practice tasks.",
     "desc": "PTE Academic with AI-scored Repeat Sentence / Describe Image drills and full mocks.",
     "difficulty": "experienced", "price": 5999,
     "testimonial": ("Anil T.", "PTE 79 overall", "Scored 79 in my second attempt.")},
    {"cat": "BBA", "title": "BBA Entrance", "tag": "Pokhara & Kathmandu Univ. focus.",
     "desc": "BBA entrance with English, Quant, GK, and Logical Reasoning drills.",
     "difficulty": "scratch", "price": 2499,
     "testimonial": ("Prakash R.", "KU BBA 2024", "Loved the explanations after each mock.")},

    # Tech (blue)
    {"cat": "Data Analysis", "title": "SQL for Analysts", "tag": "From SELECT to window functions.",
     "desc": "Hands-on SQL with PostgreSQL — real business datasets, 40+ exercises.",
     "difficulty": "scratch", "price": 4999, "featured": True,
     "testimonial": ("Nisha M.", "Analyst @ fintech", "Landed my first analyst job 3 months after finishing.")},
    {"cat": "Data Science", "title": "Data Science Bootcamp", "tag": "Python · pandas · scikit-learn · ML.",
     "desc": "16-week bootcamp — Python, pandas, visualization, and applied ML on real datasets.",
     "difficulty": "experienced", "price": 14999,
     "testimonial": ("Bibek L.", "DS Intern", "The projects got me my internship interviews.")},

    # Kids (neon/magenta)
    {"cat": "Scratch for Kids", "title": "Scratch: First Games", "tag": "Build 5 games, ages 8–12.",
     "desc": "Make 5 playable games in Scratch — no typing required. For ages 8–12.",
     "difficulty": "kid", "price": 1999, "featured": True,
     "testimonial": ("Ayush (age 11)", "Kid Innovator", "I made a flying cat game!")},
    {"cat": "Python for Kids", "title": "Python: First Scripts", "tag": "Ages 10–14, real code.",
     "desc": "Write your first real Python programs — turtle graphics, simple games, and a chatbot.",
     "difficulty": "kid", "price": 2499,
     "testimonial": ("Riya (age 13)", "Kid Innovator", "I built a quiz game for my class!")},
    {"cat": "AI for Kids", "title": "AI: First Models", "tag": "Teachable Machine · ethics · projects.",
     "desc": "Kids train their own image/sound classifiers and explore AI ethics through projects.",
     "difficulty": "kid", "price": 2999,
     "testimonial": ("Sanjay (age 14)", "Kid Innovator", "My model tells cats from dogs!")},
]


CATEGORY_DEFS = {
    "CMAT":            ("entrance", "circle",   "green"),
    "BSc CSIT":        ("entrance", "square",   "green"),
    "IELTS":           ("entrance", "hexagon",  "green"),
    "PTE":             ("entrance", "triangle", "green"),
    "BBA":             ("entrance", "circle",   "green"),
    "Data Analysis":   ("tech",     "square",   "blue"),
    "Data Science":    ("tech",     "hexagon",  "blue"),
    "Scratch for Kids":("kids",     "triangle", "kids"),
    "Python for Kids": ("kids",     "hexagon",  "kids"),
    "AI for Kids":     ("kids",     "circle",   "kids"),
}


EXAMS = [
    ("cmat",  "CMAT Mock — Full Length",  120, 50, False, "CMAT full-length mock with sectional timing simulated."),
    ("cmat",  "CMAT — Quant Drill",        30, 20, True,  "20 quick quant questions — free preview."),
    ("csit",  "BSc CSIT Entrance Mock",   120, 60, False, "TU BSc CSIT entrance — full mock."),
    ("ielts", "IELTS Reading Mock",        60, 40, False, "Full Academic Reading mock, 3 passages."),
    ("pte",   "PTE Reading Mini Mock",     30, 15, True,  "Short PTE reading mock — free preview."),
    ("bba",   "BBA Entrance Mock",         90, 40, False, "BBA entrance with verbal, quant, GK."),
    ("bit",   "BIT Entrance Mock",         90, 40, False, "BIT entrance full mock."),
]


QUESTIONS_CMAT = [
    ("Quantitative", "If 3x + 5 = 20, what is x?", "Solve: 3x = 15, so x = 5.", [
        ("3", False), ("5", True), ("7", False), ("15", False)]),
    ("Quantitative", "The average of 10, 20, 30, 40 is:", "Sum = 100, /4 = 25.", [
        ("20", False), ("25", True), ("30", False), ("35", False)]),
    ("Verbal", "Choose the synonym of 'benevolent':", "'Benevolent' means kind and generous.", [
        ("Malicious", False), ("Kind", True), ("Indifferent", False), ("Arrogant", False)]),
    ("Logical", "Find the next number: 2, 6, 12, 20, __", "Differences: 4, 6, 8, then 10 → 30.", [
        ("24", False), ("28", False), ("30", True), ("36", False)]),
    ("GK", "The capital of Nepal is:", "Kathmandu is the capital of Nepal.", [
        ("Pokhara", False), ("Biratnagar", False), ("Kathmandu", True), ("Lalitpur", False)]),
]

QUESTIONS_IELTS = [
    ("Reading", "Choose the word closest in meaning to 'mitigate':", "'Mitigate' means to make less severe.", [
        ("Worsen", False), ("Alleviate", True), ("Ignore", False), ("Delay", False)]),
    ("Listening", "In a lecture, the speaker says 'furthermore' to:", "'Furthermore' adds another point.", [
        ("Contrast an idea", False), ("Add information", True), ("Conclude", False), ("Give an example", False)]),
    ("Grammar", "'She ___ to London last year.' Choose the correct form.", "Past simple: 'went'.", [
        ("goes", False), ("has gone", False), ("went", True), ("going", False)]),
]

QUESTIONS_PTE = [
    ("Reading", "Select the correct word: The report was ___ by the committee.", "Passive past: 'approved'.", [
        ("approve", False), ("approved", True), ("approving", False), ("approval", False)]),
    ("Writing", "Identify the best summary of: 'Many cities are investing in cycling infrastructure to reduce traffic and pollution.'",
     "Matches key points: infrastructure + benefits.", [
        ("Cities build cycling paths to cut traffic and pollution.", True),
        ("Cars cause pollution everywhere.", False),
        ("Cyclists are healthier.", False),
        ("Pollution is bad.", False)]),
    ("Listening", "'Ubiquitous' most nearly means:", "Means everywhere, widespread.", [
        ("Rare", False), ("Widespread", True), ("Loud", False), ("Hidden", False)]),
]


QUESTION_BANK = {
    "cmat":  QUESTIONS_CMAT,
    "ielts": QUESTIONS_IELTS,
    "pte":   QUESTIONS_PTE,
}


CURRICULUM = {
    "Scratch: First Games": [
        ("Getting Started", [
            ("Meet the Scratch editor", "video", "https://www.youtube.com/embed/jXUZaf5D12A", 8, True),
            ("Sprites and backdrops", "video", "https://www.youtube.com/embed/YAy-ONSs0lc", 10, False),
        ]),
        ("Your First Game", [
            ("Make the cat jump", "video", "https://www.youtube.com/embed/7NL90tC5elU", 12, False),
            ("Mini project: Flappy Cat", "project", "", 30, False),
        ]),
    ],
    "Python: First Scripts": [
        ("Hello, Python", [
            ("Install and run Python", "video", "https://www.youtube.com/embed/kqtD5dpn9C8", 9, True),
            ("Variables and print", "video", "https://www.youtube.com/embed/cQT33yu9pY8", 11, False),
        ]),
        ("Fun with turtle", [
            ("Draw a square", "video", "https://www.youtube.com/embed/mRMNf-PkoHo", 10, False),
            ("Mini project: Spirograph", "project", "", 25, False),
        ]),
    ],
    "AI: First Models": [
        ("What is AI?", [
            ("Intro to AI for kids", "video", "https://www.youtube.com/embed/mJeNghZXtMo", 8, True),
            ("Teachable Machine tour", "video", "https://www.youtube.com/embed/T2qQGqZxkD0", 10, False),
        ]),
        ("Train your first model", [
            ("Cats vs dogs classifier", "project", "", 30, False),
        ]),
    ],
    "SQL for Analysts": [
        ("SQL Basics", [
            ("SELECT and WHERE", "video", "https://www.youtube.com/embed/27axs9dO7AE", 15, True),
            ("JOINs explained", "video", "https://www.youtube.com/embed/9yeOJ0ZMUYw", 18, False),
        ]),
        ("Advanced SQL", [
            ("Window functions", "article", "", 20, False),
        ]),
    ],
    "Data Science Bootcamp": [
        ("Python for DS", [
            ("pandas basics", "video", "https://www.youtube.com/embed/vmEHCJofslg", 20, True),
        ]),
        ("Applied ML", [
            ("scikit-learn quickstart", "video", "https://www.youtube.com/embed/0Lt9w-BxKFQ", 22, False),
            ("Capstone: Titanic", "project", "", 45, False),
        ]),
    ],
}


BADGES = [
    ("First Steps", "Completed your first lesson.", "circle", "kids"),
    ("Course Finisher", "Completed a whole course.", "hexagon", "entrance"),
    ("Project Builder", "Shipped your first project.", "triangle", "tech"),
    ("Mock Champ", "Scored 80%+ on a mock exam.", "square", "entrance"),
]


PLANS = [
    ("Free Taste", "Try before you buy", 0, 7, "monthly", False,
     ["Free preview mocks", "Access to 1 course intro", "Community support"]),
    ("CMAT Pro", "Everything for CMAT aspirants", 1499, 30, "monthly", True,
     ["Unlimited CMAT mocks", "All explanations", "Weekly live doubt sessions", "Performance analytics"]),
    ("All Access", "Entrance + Tech + Kids", 2999, 30, "monthly", False,
     ["Everything in CMAT Pro", "All Entrance exams (CSIT, BBA, IELTS, PTE)", "Tech upskilling courses", "Kids' Summer Camp access"]),
    ("Annual All Access", "Save 35% yearly", 23999, 365, "yearly", False,
     ["All features", "Priority support", "Certificate of completion"]),
]


class Command(BaseCommand):
    help = "Seed demo data: categories, courses, exams, questions, plans, trust signals."

    @transaction.atomic
    def handle(self, *args, **opts):
        self.stdout.write("→ Seeding site settings…")
        SiteSettings.load()

        self.stdout.write("→ Seeding categories + courses…")
        cat_cache = {}
        for name, (pillar, shape, color) in CATEGORY_DEFS.items():
            cat, _ = Category.objects.get_or_create(
                name=name,
                defaults={"pillar": pillar, "shape": shape, "accent_color": color},
            )
            cat_cache[name] = cat

        for c in COURSES:
            course, created = Course.objects.get_or_create(
                title=c["title"],
                defaults={
                    "category": cat_cache[c["cat"]],
                    "tagline": c["tag"],
                    "description": c["desc"],
                    "difficulty": c["difficulty"],
                    "price_npr": c["price"],
                    "is_featured": c.get("featured", False),
                },
            )
            if created and c.get("testimonial"):
                name_, title_, quote = c["testimonial"]
                Testimonial.objects.create(
                    course=course, student_name=name_, student_title=title_,
                    quote=quote, is_featured=True,
                )

        self.stdout.write("→ Seeding modules + lessons…")
        for title, modules in CURRICULUM.items():
            try:
                course = Course.objects.get(title=title)
            except Course.DoesNotExist:
                continue
            for m_idx, (m_title, lessons) in enumerate(modules):
                module, _ = Module.objects.get_or_create(
                    course=course, title=m_title,
                    defaults={"order": m_idx},
                )
                for l_idx, (l_title, kind, url, mins, free) in enumerate(lessons):
                    Lesson.objects.get_or_create(
                        module=module, title=l_title,
                        defaults={
                            "kind": kind, "video_url": url,
                            "duration_minutes": mins, "order": l_idx,
                            "is_free_preview": free,
                        },
                    )

        self.stdout.write("→ Seeding badges…")
        for name, desc, shape, color in BADGES:
            Badge.objects.get_or_create(
                name=name,
                defaults={"description": desc, "icon_shape": shape, "color": color},
            )

        self.stdout.write("→ Seeding trust signals + success stats…")
        trust = [
            ("Practice, then explain.", "Every wrong answer comes with a full explanation — right after you submit.", "circle"),
            ("Built mobile-first.", "Works on a cheap Android, tested on slow networks.", "square"),
            ("Kids don't hate it.", "Badges, big buttons, and real projects kids can show a parent.", "triangle"),
        ]
        for i, (t, b, icon) in enumerate(trust):
            TrustSignal.objects.get_or_create(title=t, defaults={"body": b, "icon": icon, "order": i})

        stats = [("Learners onboarded", "12,000+"), ("CMAT pass rate", "94%"),
                 ("Avg IELTS band", "7.5"), ("Kids shipping AI projects", "250+")]
        for i, (label, value) in enumerate(stats):
            SuccessStat.objects.get_or_create(label=label, defaults={"value": value, "order": i})

        self.stdout.write("→ Seeding plans…")
        for i, (name, tagline, price, days, interval, popular, features) in enumerate(PLANS):
            Plan.objects.get_or_create(
                name=name,
                defaults={
                    "tagline": tagline, "price_npr": price, "duration_days": days,
                    "interval": interval, "is_popular": popular, "order": i,
                    "features": "\n".join(features),
                },
            )

        self.stdout.write("→ Seeding exams + questions…")
        for etype, name, duration, qcount, is_free, desc in EXAMS:
            exam, created = Exam.objects.get_or_create(
                name=name,
                defaults={
                    "exam_type": etype, "duration_minutes": duration,
                    "total_questions": qcount, "description": desc,
                    "is_free_preview": is_free,
                    "requires_subscription": not is_free,
                    "pass_percentage": 40,
                },
            )
            if created and etype in QUESTION_BANK:
                for idx, (section, text, expl, choices) in enumerate(QUESTION_BANK[etype]):
                    q = Question.objects.create(
                        exam=exam, text=text, explanation=expl,
                        section=section, order=idx,
                    )
                    for cidx, (ctext, correct) in enumerate(choices):
                        Choice.objects.create(
                            question=q, text=ctext, is_correct=correct, order=cidx,
                        )

        self.stdout.write(self.style.SUCCESS("✓ Seed complete."))
