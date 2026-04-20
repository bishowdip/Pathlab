from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("search/", views.search, name="search"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("instructors/", views.instructors_directory, name="instructors"),
    path("staff/", views.staff_dashboard, name="staff_dashboard"),
]
