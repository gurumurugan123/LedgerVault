from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ledger.models import Payment, PaymentStatus, calculate_wallet_balance
from apps.users.models import User
from apps.users.permissions import IsSupport
from apps.wallets.models import Wallet
from apps.wallets.serializers import WalletSerializer


class SupportUserLookupView(APIView):
    permission_classes = [IsAuthenticated, IsSupport]

    def get(self, request):
        email = request.query_params.get("email", "").strip()
        if not email:
            return Response(
                {"detail": "Query parameter 'email' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "wallet_count": user.wallets.count(),
                "created_at": user.created_at,
            }
        )


class SupportWalletLookupView(APIView):
    permission_classes = [IsAuthenticated, IsSupport]

    def get(self, request):
        email = request.query_params.get("email", "").strip()
        if not email:
            return Response(
                {"detail": "Query parameter 'email' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        wallets = Wallet.objects.filter(user=user).order_by("id")
        results = []
        for wallet in wallets:
            data = WalletSerializer(wallet).data
            data["balance"] = str(calculate_wallet_balance(wallet.id))
            results.append(data)

        return Response({"email": user.email, "wallets": results})


class SupportPaymentListView(APIView):
    permission_classes = [IsAuthenticated, IsSupport]

    def get(self, request):
        status_filter = request.query_params.get("status", "").strip().upper()
        queryset = Payment.objects.select_related("wallet", "wallet__user").order_by("-created_at")

        if status_filter:
            if status_filter not in PaymentStatus.values:
                return Response(
                    {
                        "detail": f"Invalid status. Choose from: {', '.join(PaymentStatus.values)}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=status_filter)

        results = [
            {
                "id": payment.id,
                "external_id": payment.external_id,
                "wallet_id": payment.wallet_id,
                "user_email": payment.wallet.user.email,
                "direction": payment.direction,
                "amount": str(payment.amount),
                "status": payment.status,
                "transaction_id": payment.transaction_id,
                "created_at": payment.created_at,
            }
            for payment in queryset
        ]
        return Response(results)
