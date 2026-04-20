from django.urls import path
from . import views

urlpatterns = [
    path("", views.pricing, name="pricing"),
    path("mine/", views.my_subscription, name="my_subscription"),
    path("mine/<int:pk>/cancel/", views.cancel_subscription, name="cancel_subscription"),
    path("receipt/<int:payment_id>/", views.receipt, name="receipt"),
    path("checkout/<slug:slug>/", views.checkout, name="checkout"),

    path("payment/esewa/<int:payment_id>/", views.esewa_init, name="esewa_init"),
    path("payment/esewa/success/", views.esewa_success, name="esewa_success"),
    path("payment/esewa/failure/", views.esewa_failure, name="esewa_failure"),

    path("payment/khalti/<int:payment_id>/", views.khalti_init, name="khalti_init"),
    path("payment/khalti/<int:payment_id>/verify/", views.khalti_verify, name="khalti_verify"),

    path("payment/stripe/<int:payment_id>/", views.stripe_init, name="stripe_init"),
    path("payment/stripe/<int:payment_id>/success/", views.stripe_success, name="stripe_success"),

    path("payment/paypal/<int:payment_id>/", views.paypal_init, name="paypal_init"),
    path("payment/paypal/<int:payment_id>/success/", views.paypal_success, name="paypal_success"),
]
