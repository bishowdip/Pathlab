from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.courses.models import Course, Instructor


class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return ["core:home", "core:about", "core:contact", "core:instructors",
                "core:terms", "core:privacy",
                "courses:list", "exams:list", "subscriptions:pricing"]

    def location(self, item):
        return reverse(item)


class CourseSitemap(Sitemap):
    priority = 0.9
    changefreq = "weekly"

    def items(self):
        return Course.objects.filter(published=True)

    def location(self, obj):
        return obj.get_absolute_url()


class InstructorSitemap(Sitemap):
    priority = 0.6
    changefreq = "monthly"

    def items(self):
        return Instructor.objects.all()

    def location(self, obj):
        return obj.get_absolute_url()


sitemaps = {
    "static": StaticViewSitemap,
    "courses": CourseSitemap,
    "instructors": InstructorSitemap,
}
