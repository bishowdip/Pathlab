from django.urls import path
from . import views

app_name = "support"

urlpatterns = [
    path("", views.widget_page, name="chat"),
    path("api/send/", views.api_send, name="api_send"),
    path("api/poll/", views.api_poll, name="api_poll"),
    path("threads/", views.thread_list, name="thread_list"),
    path("threads/<int:thread_id>/", views.thread_detail, name="thread_detail"),
]
