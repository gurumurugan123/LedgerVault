from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.ledger.exceptions import (
    InsufficientBalanceError,
    InvalidPaymentError,
    InvalidTransferError,
    PaymentNotFoundError,
    WalletAccessDeniedError,
    WalletNotFoundError,
    WebhookSignatureError,
)
from apps.ledger.models import (
    EntryStatus,
    EntryType,
    IdempotencyKey,
    LedgerEntry,
    Payment,
    PaymentDirection,
    PaymentStatus,
    Transaction,
    TransactionType,
    calculate_available_balance,
    calculate_wallet_balance,
)
from apps.ledger.payment_provider import (
    generate_external_payment_id,
    verify_webhook_signature,
)
from apps.wallets.models import Wallet


def _build_payment_response(payment: Payment) -> dict:
    return {
        "payment_id": payment.id,
        "external_id": payment.external_id,
        "transaction_id": payment.transaction_id,
        "type": payment.direction,
        "wallet_id": payment.wallet_id,
        "amount": str(payment.amount),
        "status": payment.status,
        "balance": str(calculate_wallet_balance(payment.wallet_id)),
        "available_balance": str(calculate_available_balance(payment.wallet_id)),
    }


def _initiate_topup_locked(*, user, wallet_id: int, amount: Decimal) -> dict:
    try:
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
    except Wallet.DoesNotExist as exc:
        raise WalletNotFoundError(f"Wallet not found: {wallet_id}") from exc

    if wallet.user_id != user.id:
        raise WalletAccessDeniedError("You do not own this wallet.")

    topup_tx = Transaction.objects.create(type=TransactionType.TOPUP)
    LedgerEntry.objects.create(
        wallet=wallet,
        type=EntryType.CREDIT,
        amount=amount,
        transaction=topup_tx,
        status=EntryStatus.PENDING,
    )
    payment = Payment.objects.create(
        external_id=generate_external_payment_id(),
        wallet=wallet,
        direction=PaymentDirection.TOPUP,
        amount=amount,
        status=PaymentStatus.PENDING,
        transaction=topup_tx,
    )
    return _build_payment_response(payment)


def _initiate_withdrawal_locked(*, user, wallet_id: int, amount: Decimal) -> dict:
    try:
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
    except Wallet.DoesNotExist as exc:
        raise WalletNotFoundError(f"Wallet not found: {wallet_id}") from exc

    if wallet.user_id != user.id:
        raise WalletAccessDeniedError("You do not own this wallet.")

    available = calculate_available_balance(wallet.id)
    if available < amount:
        raise InsufficientBalanceError(
            f"Insufficient available balance. Available: {available}, requested: {amount}."
        )

    withdrawal_tx = Transaction.objects.create(type=TransactionType.WITHDRAWAL)
    LedgerEntry.objects.create(
        wallet=wallet,
        type=EntryType.DEBIT,
        amount=amount,
        transaction=withdrawal_tx,
        status=EntryStatus.PENDING,
    )
    payment = Payment.objects.create(
        external_id=generate_external_payment_id(),
        wallet=wallet,
        direction=PaymentDirection.WITHDRAWAL,
        amount=amount,
        status=PaymentStatus.PENDING,
        transaction=withdrawal_tx,
    )
    return _build_payment_response(payment)


def _execute_idempotent_payment(*, idempotency_key: str, executor):
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
            response_body = executor()
        except Exception:
            if record.status_code == 0:
                record.delete()
            raise

        record.response_body = response_body
        record.status_code = 201
        record.save(update_fields=["response_body", "status_code"])
        return 201, response_body


def execute_idempotent_topup(*, idempotency_key: str, user, wallet_id: int, amount) -> tuple[int, dict]:
    amount = Decimal(str(amount))
    if amount <= Decimal("0"):
        raise InvalidTransferError("Amount must be greater than zero.")

    return _execute_idempotent_payment(
        idempotency_key=idempotency_key,
        executor=lambda: _initiate_topup_locked(user=user, wallet_id=wallet_id, amount=amount),
    )


def execute_idempotent_withdrawal(*, idempotency_key: str, user, wallet_id: int, amount) -> tuple[int, dict]:
    amount = Decimal(str(amount))
    if amount <= Decimal("0"):
        raise InvalidTransferError("Amount must be greater than zero.")

    return _execute_idempotent_payment(
        idempotency_key=idempotency_key,
        executor=lambda: _initiate_withdrawal_locked(user=user, wallet_id=wallet_id, amount=amount),
    )


def process_payment_webhook(
    *,
    event_id: str,
    external_id: str,
    payment_status: str,
    raw_body: bytes,
    signature: str,
) -> dict:
    if not verify_webhook_signature(raw_body, signature):
        raise WebhookSignatureError("Invalid webhook signature.")

    normalized_status = payment_status.lower().strip()
    if normalized_status not in {"completed", "failed"}:
        raise InvalidPaymentError("status must be 'completed' or 'failed'.")

    with transaction.atomic():
        existing_event = Payment.objects.filter(webhook_event_id=event_id).first()
        if existing_event:
            return _build_payment_response(existing_event)

        try:
            payment = (
                Payment.objects.select_for_update()
                .select_related("wallet", "transaction")
                .get(external_id=external_id)
            )
        except Payment.DoesNotExist as exc:
            raise PaymentNotFoundError(f"Payment not found: {external_id}") from exc

        if payment.status != PaymentStatus.PENDING:
            return _build_payment_response(payment)

        entry = (
            LedgerEntry.objects.select_for_update()
            .filter(transaction=payment.transaction)
            .first()
        )
        if entry is None:
            raise InvalidPaymentError("Payment has no ledger entry.")

        if normalized_status == "completed":
            entry.status = EntryStatus.CONFIRMED
            entry.save(update_fields=["status"])
            payment.status = PaymentStatus.COMPLETED
        else:
            entry.delete()
            payment.status = PaymentStatus.FAILED

        payment.webhook_event_id = event_id
        payment.save(update_fields=["status", "webhook_event_id", "updated_at"])
        return _build_payment_response(payment)
