from django.db.models import Prefetch

from apps.ledger.models import LedgerEntry, Transaction
from apps.wallets.models import Wallet


def get_user_transactions(user):
    wallet_ids = Wallet.objects.filter(user=user).values_list("id", flat=True)
    transaction_ids = (
        LedgerEntry.objects.filter(wallet_id__in=wallet_ids)
        .values_list("transaction_id", flat=True)
        .distinct()
    )
    return (
        Transaction.objects.filter(id__in=transaction_ids)
        .prefetch_related(
            Prefetch(
                "entries",
                queryset=LedgerEntry.objects.select_related("wallet").order_by("id"),
            ),
            "reversals",
        )
        .order_by("-created_at")
    )


def user_can_view_transaction(user, transaction_id: int) -> bool:
    wallet_ids = Wallet.objects.filter(user=user).values_list("id", flat=True)
    return LedgerEntry.objects.filter(
        transaction_id=transaction_id,
        wallet_id__in=wallet_ids,
    ).exists()


def serialize_transaction(transaction: Transaction) -> dict:
    entries = []
    for entry in transaction.entries.all():
        entries.append(
            {
                "id": entry.id,
                "wallet_id": entry.wallet_id,
                "type": entry.type,
                "amount": str(entry.amount),
                "status": entry.status,
                "created_at": entry.created_at,
            }
        )

    return {
        "id": transaction.id,
        "type": transaction.type,
        "reference_transaction_id": transaction.reference_transaction_id,
        "reversal_ids": list(transaction.reversals.values_list("id", flat=True)),
        "entries": entries,
        "created_at": transaction.created_at,
    }
