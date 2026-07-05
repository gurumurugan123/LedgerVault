from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.ledger.exceptions import (
    InsufficientBalanceError,
    InvalidReversalError,
    TransactionNotFoundError,
)
from apps.ledger.models import (
    EntryStatus,
    EntryType,
    IdempotencyKey,
    LedgerEntry,
    Transaction,
    TransactionType,
    calculate_wallet_balance,
)
from apps.wallets.models import Wallet


def _build_reversal_response(reversal_tx: Transaction, original_tx: Transaction) -> dict:
    affected_wallets = []
    for entry in reversal_tx.entries.select_related("wallet"):
        affected_wallets.append(
            {
                "wallet_id": entry.wallet_id,
                "entry_type": entry.type,
                "amount": str(entry.amount),
                "balance": str(calculate_wallet_balance(entry.wallet_id)),
            }
        )

    return {
        "reversal_transaction_id": reversal_tx.id,
        "original_transaction_id": original_tx.id,
        "original_type": original_tx.type,
        "type": reversal_tx.type,
        "affected_wallets": affected_wallets,
    }


def _execute_reversal_locked(*, transaction_id: int) -> dict:
    try:
        original = Transaction.objects.select_for_update().get(id=transaction_id)
    except Transaction.DoesNotExist as exc:
        raise TransactionNotFoundError(f"Transaction not found: {transaction_id}") from exc

    if original.type == TransactionType.REVERSAL:
        raise InvalidReversalError("Cannot reverse a reversal transaction.")

    if original.type not in (
        TransactionType.TRANSFER,
        TransactionType.TOPUP,
        TransactionType.WITHDRAWAL,
    ):
        raise InvalidReversalError(f"Transaction type {original.type} cannot be reversed.")

    if original.reversals.exists():
        raise InvalidReversalError("Transaction has already been reversed.")

    entries = list(
        LedgerEntry.objects.select_for_update()
        .filter(transaction=original)
        .select_related("wallet")
    )
    if not entries:
        raise InvalidReversalError("Transaction has no ledger entries.")

    if any(entry.status != EntryStatus.CONFIRMED for entry in entries):
        raise InvalidReversalError("Only fully confirmed transactions can be reversed.")

    wallet_ids = sorted({entry.wallet_id for entry in entries})
    locked_wallets = Wallet.objects.select_for_update().filter(id__in=wallet_ids)
    if locked_wallets.count() != len(wallet_ids):
        raise InvalidReversalError("One or more wallets for this transaction no longer exist.")

    for entry in entries:
        opposite_type = EntryType.CREDIT if entry.type == EntryType.DEBIT else EntryType.DEBIT
        if opposite_type == EntryType.DEBIT:
            available = calculate_wallet_balance(entry.wallet_id)
            if available < entry.amount:
                raise InsufficientBalanceError(
                    f"Insufficient balance to reverse wallet {entry.wallet_id}. "
                    f"Available: {available}, required: {entry.amount}."
                )

    reversal_tx = Transaction.objects.create(
        type=TransactionType.REVERSAL,
        reference_transaction=original,
    )

    for entry in entries:
        opposite_type = EntryType.CREDIT if entry.type == EntryType.DEBIT else EntryType.DEBIT
        LedgerEntry.objects.create(
            wallet_id=entry.wallet_id,
            type=opposite_type,
            amount=entry.amount,
            transaction=reversal_tx,
            status=EntryStatus.CONFIRMED,
        )

    return _build_reversal_response(reversal_tx, original)


def execute_idempotent_reversal(*, idempotency_key: str, transaction_id: int) -> tuple[int, dict]:
    transaction_id = int(transaction_id)

    with transaction.atomic():
        record = (
            IdempotencyKey.objects.select_for_update()
            .filter(key=idempotency_key)
            .first()
        )
        if record and record.status_code != 0:
            return record.status_code, record.response_body

        if record is None:
            try:
                with transaction.atomic():
                    record = IdempotencyKey.objects.create(
                        key=idempotency_key,
                        response_body={},
                        status_code=0,
                    )
            except IntegrityError:
                record = IdempotencyKey.objects.select_for_update().get(key=idempotency_key)
                if record.status_code != 0:
                    return record.status_code, record.response_body

        if record.status_code != 0:
            return record.status_code, record.response_body

        try:
            response_body = _execute_reversal_locked(transaction_id=transaction_id)
        except Exception:
            if record.status_code == 0:
                record.delete()
            raise

        record.response_body = response_body
        record.status_code = 201
        record.save(update_fields=["response_body", "status_code"])
        return 201, response_body
