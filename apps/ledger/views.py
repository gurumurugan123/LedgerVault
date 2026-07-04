from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ledger.exceptions import (
    InsufficientBalanceError,
    InvalidTransferError,
    TransferError,
    WalletAccessDeniedError,
    WalletNotFoundError,
)
from apps.ledger.serializers import TransferSerializer
from apps.ledger.services import execute_idempotent_transfer

IDEMPOTENCY_HEADER = "Idempotency-Key"


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
        except WalletAccessDeniedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except WalletNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except InsufficientBalanceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except InvalidTransferError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except TransferError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(response_body, status=status_code)
