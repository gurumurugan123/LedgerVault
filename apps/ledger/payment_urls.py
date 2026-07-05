from django.urls import path

from apps.ledger.views import PaymentWebhookView, TopUpView, WithdrawView

urlpatterns = [
    path("topups/", TopUpView.as_view(), name="topup-create"),
    path("withdrawals/", WithdrawView.as_view(), name="withdraw-create"),
    path("webhooks/payments/", PaymentWebhookView.as_view(), name="payment-webhook"),
]
