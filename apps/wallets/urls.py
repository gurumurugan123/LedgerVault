from django.urls import path

from apps.wallets.views import WalletBalanceView, WalletLedgerView, WalletListCreateView

urlpatterns = [
    path("", WalletListCreateView.as_view(), name="wallet-list-create"),
    path("<int:pk>/balance/", WalletBalanceView.as_view(), name="wallet-balance"),
    path("<int:pk>/ledger/", WalletLedgerView.as_view(), name="wallet-ledger"),
]
