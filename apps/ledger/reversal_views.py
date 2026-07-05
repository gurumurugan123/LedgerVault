from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ledger.exceptions import (
    InsufficientBalanceError,
    InvalidReversalError,
    ReversalError,
    TransactionNotFoundError,
)
from apps.ledger.reversal_services import execute_idempotent_reversal
from apps.ledger.serializers import ReversalSerializer
from apps.ledger.views import IDEMPOTENCY_HEADER
from apps.users.permissions import IsSupport


def _map_reversal_errors(exc):
    if isinstance(exc, TransactionNotFoundError):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, (InsufficientBalanceError, InvalidReversalError, ReversalError)):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    raise exc


class ReversalView(APIView):
    permission_classes = [IsAuthenticated, IsSupport]

    def post(self, request):
        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
        if not idempotency_key or not idempotency_key.strip():
            return Response(
                {"detail": f"{IDEMPOTENCY_HEADER} header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ReversalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            status_code, response_body = execute_idempotent_reversal(
                idempotency_key=idempotency_key.strip(),
                transaction_id=serializer.validated_data["transaction_id"],
            )
        except InsufficientBalanceError as exc:
            return _map_reversal_errors(exc)
        except ReversalError as exc:
            return _map_reversal_errors(exc)

        from apps.ledger.audit_service import log_audit
        from apps.ledger.models import AuditAction

        log_audit(
            actor=request.user,
            action=AuditAction.REVERSAL_CREATED,
            target_type="transaction",
            target_id=response_body["original_transaction_id"],
            metadata={
                "reversal_transaction_id": response_body["reversal_transaction_id"],
                "original_type": response_body["original_type"],
            },
        )

        return Response(response_body, status=status_code)
