from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ledger.transaction_services import (
    get_user_transactions,
    serialize_transaction,
    user_can_view_transaction,
)


class TransactionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        transactions = get_user_transactions(request.user)
        return Response([serialize_transaction(tx) for tx in transactions])


class TransactionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not user_can_view_transaction(request.user, pk):
            return Response({"detail": "Transaction not found."}, status=status.HTTP_404_NOT_FOUND)

        transaction = get_object_or_404(
            get_user_transactions(request.user),
            pk=pk,
        )
        return Response(serialize_transaction(transaction))
