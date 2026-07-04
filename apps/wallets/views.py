from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ledger.models import LedgerEntry, calculate_wallet_balance
from apps.wallets.models import Wallet
from apps.wallets.permissions import IsWalletOwner
from apps.wallets.serializers import (
    LedgerEntrySerializer,
    WalletBalanceSerializer,
    WalletSerializer,
)


class WalletPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class WalletScopedMixin:
    wallet_url_kwarg = "pk"

    def get_wallet(self):
        if not hasattr(self, "_wallet"):
            self._wallet = generics.get_object_or_404(
                Wallet.objects.filter(user=self.request.user),
                pk=self.kwargs[self.wallet_url_kwarg],
            )
            self.check_object_permissions(self.request, self._wallet)
        return self._wallet


class WalletListCreateView(generics.ListCreateAPIView):
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Wallet.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class WalletBalanceView(WalletScopedMixin, generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsWalletOwner]

    def get_object(self):
        return self.get_wallet()

    def get(self, request, *args, **kwargs):
        wallet = self.get_wallet()
        balance = calculate_wallet_balance(wallet.id)
        data = {
            "wallet_id": wallet.id,
            "currency": wallet.currency,
            "balance": balance,
        }
        return Response(WalletBalanceSerializer(data).data)


class WalletLedgerView(WalletScopedMixin, generics.ListAPIView):
    serializer_class = LedgerEntrySerializer
    permission_classes = [IsAuthenticated, IsWalletOwner]
    pagination_class = WalletPagination

    def get_queryset(self):
        wallet = self.get_wallet()
        return LedgerEntry.objects.filter(wallet=wallet).select_related("transaction")
