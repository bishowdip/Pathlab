from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

from apps.core.sitemaps import sitemaps

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
    path("", include(("apps.core.urls", "core"), namespace="core")),
    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("courses/", include(("apps.courses.urls", "courses"), namespace="courses")),
    path("exams/", include(("apps.exams.urls", "exams"), namespace="exams")),
    path("subscriptions/", include(("apps.subscriptions.urls", "subscriptions"), namespace="subscriptions")),
    path("support/", include("apps.support.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
