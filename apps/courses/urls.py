from django.urls import path
from . import views
from .instructor import views as iviews

urlpatterns = [
    path("", views.course_list, name="list"),
    path("resource/<int:resource_id>/", views.resource_download, name="resource_download"),
    path("instructor/<slug:slug>/", views.instructor_detail, name="instructor_detail"),

    # ---- Instructor workspace (namespaced under /teach/) ----
    path("teach/", iviews.dashboard, name="instructor_dashboard"),
    path("teach/students/", iviews.students, name="instructor_students"),
    # Staff editorial review (not instructor-accessible).
    path("review/", iviews.review_queue, name="review_queue"),
    path("review/<slug:slug>/approve/", iviews.review_approve, name="review_approve"),
    path("review/<slug:slug>/changes/", iviews.review_request_changes, name="review_request_changes"),
    path("teach/denied/", iviews.denied, name="instructor_denied"),
    path("teach/new/", iviews.course_create, name="instructor_course_create"),
    path("teach/<slug:slug>/", iviews.course_manage, name="instructor_course_manage"),
    path("teach/<slug:slug>/edit/", iviews.course_edit, name="instructor_course_edit"),
    path("teach/<slug:slug>/delete/", iviews.course_delete, name="instructor_course_delete"),
    path("teach/<slug:slug>/publish/", iviews.course_toggle_publish, name="instructor_course_publish"),
    path("teach/<slug:course_slug>/modules/new/", iviews.module_create, name="instructor_module_create"),
    path("teach/<slug:course_slug>/modules/<int:module_id>/edit/", iviews.module_edit, name="instructor_module_edit"),
    path("teach/<slug:course_slug>/modules/<int:module_id>/delete/", iviews.module_delete, name="instructor_module_delete"),
    path("teach/<slug:course_slug>/modules/<int:module_id>/lessons/new/",
         iviews.lesson_create, name="instructor_lesson_create"),
    path("teach/<slug:course_slug>/modules/<int:module_id>/lessons/<int:lesson_id>/edit/",
         iviews.lesson_edit, name="instructor_lesson_edit"),
    path("teach/<slug:course_slug>/modules/<int:module_id>/lessons/<int:lesson_id>/delete/",
         iviews.lesson_delete, name="instructor_lesson_delete"),
    path("teach/<slug:course_slug>/modules/<int:module_id>/lessons/<int:lesson_id>/resources/upload/",
         iviews.resource_upload, name="instructor_resource_upload"),
    path("teach/<slug:course_slug>/modules/<int:module_id>/lessons/<int:lesson_id>/resources/<int:resource_id>/delete/",
         iviews.resource_delete, name="instructor_resource_delete"),

    path("<slug:slug>/", views.course_detail, name="detail"),
    path("<slug:slug>/enroll/", views.enroll, name="enroll"),
    path("<slug:slug>/review/", views.post_review, name="post_review"),
    path("<slug:slug>/certificate/", views.certificate, name="certificate"),
    path("<slug:slug>/certificate.pdf", views.certificate_pdf, name="certificate_pdf"),
    path(
        "<slug:course_slug>/m/<int:module_id>/<slug:lesson_slug>/note/",
        views.save_note, name="save_note",
    ),
    path(
        "<slug:course_slug>/m/<int:module_id>/<slug:lesson_slug>/",
        views.lesson_view, name="lesson",
    ),
    path(
        "<slug:course_slug>/m/<int:module_id>/<slug:lesson_slug>/video/",
        views.lesson_video, name="lesson_video",
    ),
    path(
        "<slug:course_slug>/m/<int:module_id>/<slug:lesson_slug>/complete/",
        views.mark_lesson_complete, name="lesson_complete",
    ),
]
