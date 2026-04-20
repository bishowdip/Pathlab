from django.urls import path
from . import views

urlpatterns = [
    path("", views.exam_list, name="list"),
    path("<slug:slug>/", views.exam_detail, name="detail"),
    path("<slug:slug>/start/", views.start_attempt, name="start"),
    path("<slug:slug>/leaderboard/", views.leaderboard, name="leaderboard"),
    path("take/<int:attempt_id>/", views.take_exam, name="take"),
    path("take/<int:attempt_id>/submit/", views.submit_attempt, name="submit"),
    path("result/<int:attempt_id>/", views.result, name="result"),
]
