from django.urls import path

from apps.ledger.support_views import (
    SupportPaymentListView,
    SupportUserLookupView,
    SupportWalletLookupView,
)

urlpatterns = [
    path("users/", SupportUserLookupView.as_view(), name="support-user-lookup"),
    path("wallets/", SupportWalletLookupView.as_view(), name="support-wallet-lookup"),
    path("payments/", SupportPaymentListView.as_view(), name="support-payment-list"),
]
