from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ledger.exceptions import (
    InsufficientBalanceError,
    InvalidPaymentError,
    InvalidTransferError,
    PaymentNotFoundError,
    TransferError,
    WalletAccessDeniedError,
    WalletNotFoundError,
    WebhookSignatureError,
)
from apps.ledger.payment_services import (
    execute_idempotent_topup,
    execute_idempotent_withdrawal,
    process_payment_webhook,
)
from apps.ledger.serializers import (
    PaymentWebhookSerializer,
    TransferSerializer,
    WalletPaymentSerializer,
)
from apps.ledger.services import execute_idempotent_transfer

IDEMPOTENCY_HEADER = "Idempotency-Key"
WEBHOOK_SIGNATURE_HEADER = "X-Payment-Signature"


def _map_transfer_errors(exc):
    if isinstance(exc, WalletAccessDeniedError):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, WalletNotFoundError):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, (InsufficientBalanceError, InvalidTransferError, TransferError)):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    raise exc


def _map_payment_errors(exc):
    if isinstance(exc, WalletAccessDeniedError):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, WalletNotFoundError):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, PaymentNotFoundError):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, WebhookSignatureError):
        return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
    if isinstance(exc, (InsufficientBalanceError, InvalidPaymentError, InvalidTransferError)):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    raise exc


class TransferView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
        if not idempotency_key or not idempotency_key.strip():
            return Response(
                {"detail": f"{IDEMPOTENCY_HEADER} header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            status_code, response_body = execute_idempotent_transfer(
                idempotency_key=idempotency_key.strip(),
                user=request.user,
                from_wallet_id=serializer.validated_data["from_wallet_id"],
                to_wallet_id=serializer.validated_data["to_wallet_id"],
                amount=serializer.validated_data["amount"],
            )
        except TransferError as exc:
            return _map_transfer_errors(exc)

        return Response(response_body, status=status_code)


class TopUpView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
        if not idempotency_key or not idempotency_key.strip():
            return Response(
                {"detail": f"{IDEMPOTENCY_HEADER} header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = WalletPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            status_code, response_body = execute_idempotent_topup(
                idempotency_key=idempotency_key.strip(),
                user=request.user,
                wallet_id=serializer.validated_data["wallet_id"],
                amount=serializer.validated_data["amount"],
            )
        except (TransferError, InvalidPaymentError) as exc:
            return _map_payment_errors(exc)

        return Response(response_body, status=status_code)


class WithdrawView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
        if not idempotency_key or not idempotency_key.strip():
            return Response(
                {"detail": f"{IDEMPOTENCY_HEADER} header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = WalletPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            status_code, response_body = execute_idempotent_withdrawal(
                idempotency_key=idempotency_key.strip(),
                user=request.user,
                wallet_id=serializer.validated_data["wallet_id"],
                amount=serializer.validated_data["amount"],
            )
        except (TransferError, InvalidPaymentError) as exc:
            return _map_payment_errors(exc)

        return Response(response_body, status=status_code)


class PaymentWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        raw_body = request.body
        signature = request.headers.get(WEBHOOK_SIGNATURE_HEADER, "")

        serializer = PaymentWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            response_body = process_payment_webhook(
                event_id=serializer.validated_data["event_id"],
                external_id=serializer.validated_data["payment_id"],
                payment_status=serializer.validated_data["status"],
                raw_body=raw_body,
                signature=signature,
            )
        except (PaymentNotFoundError, InvalidPaymentError, WebhookSignatureError) as exc:
            return _map_payment_errors(exc)

        return Response(response_body, status=status.HTTP_200_OK)
