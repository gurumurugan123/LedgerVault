from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.ledger.exceptions import (
    InsufficientBalanceError,
    InvalidTransferError,
    WalletAccessDeniedError,
    WalletNotFoundError,
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


def _build_transfer_response(transfer_tx, from_wallet, to_wallet, amount):
    return {
        "transaction_id": transfer_tx.id,
        "type": transfer_tx.type,
        "from_wallet_id": from_wallet.id,
        "to_wallet_id": to_wallet.id,
        "amount": str(amount),
        "from_balance": str(calculate_wallet_balance(from_wallet.id)),
        "to_balance": str(calculate_wallet_balance(to_wallet.id)),
    }


def _execute_transfer_locked(*, user, from_wallet_id: int, to_wallet_id: int, amount: Decimal) -> dict:
    """Run transfer assuming caller holds transaction.atomic() and wallet row locks."""
    wallet_ids = sorted([from_wallet_id, to_wallet_id])
    locked_wallets = Wallet.objects.select_for_update().filter(id__in=wallet_ids)
    wallets_by_id = {wallet.id: wallet for wallet in locked_wallets}

    if len(wallets_by_id) != 2:
        missing = set(wallet_ids) - set(wallets_by_id.keys())
        raise WalletNotFoundError(f"Wallet not found: {next(iter(missing))}")

    from_wallet = wallets_by_id[from_wallet_id]
    to_wallet = wallets_by_id[to_wallet_id]

    if from_wallet.user_id != user.id:
        raise WalletAccessDeniedError("You do not own the source wallet.")

    if from_wallet.currency != to_wallet.currency:
        raise InvalidTransferError("Wallets must use the same currency.")

    available = calculate_wallet_balance(from_wallet.id)
    if available < amount:
        raise InsufficientBalanceError(
            f"Insufficient balance. Available: {available}, requested: {amount}."
        )

    transfer_tx = Transaction.objects.create(type=TransactionType.TRANSFER)
    LedgerEntry.objects.create(
        wallet=from_wallet,
        type=EntryType.DEBIT,
        amount=amount,
        transaction=transfer_tx,
        status=EntryStatus.CONFIRMED,
    )
    LedgerEntry.objects.create(
        wallet=to_wallet,
        type=EntryType.CREDIT,
        amount=amount,
        transaction=transfer_tx,
        status=EntryStatus.CONFIRMED,
    )

    return _build_transfer_response(transfer_tx, from_wallet, to_wallet, amount)


def execute_transfer(*, user, from_wallet_id: int, to_wallet_id: int, amount) -> dict:
    amount = Decimal(str(amount))
    if amount <= Decimal("0"):
        raise InvalidTransferError("Amount must be greater than zero.")
    if from_wallet_id == to_wallet_id:
        raise InvalidTransferError("Cannot transfer to the same wallet.")

    with transaction.atomic():
        return _execute_transfer_locked(
            user=user,
            from_wallet_id=from_wallet_id,
            to_wallet_id=to_wallet_id,
            amount=amount,
        )


def execute_idempotent_transfer(*, idempotency_key: str, user, from_wallet_id, to_wallet_id, amount):
    amount = Decimal(str(amount))
    if amount <= Decimal("0"):
        raise InvalidTransferError("Amount must be greater than zero.")
    if from_wallet_id == to_wallet_id:
        raise InvalidTransferError("Cannot transfer to the same wallet.")

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
            response_body = _execute_transfer_locked(
                user=user,
                from_wallet_id=from_wallet_id,
                to_wallet_id=to_wallet_id,
                amount=amount,
            )
        except Exception:
            if record.status_code == 0:
                record.delete()
            raise

        record.response_body = response_body
        record.status_code = 201
        record.save(update_fields=["response_body", "status_code"])
        return 201, response_body
