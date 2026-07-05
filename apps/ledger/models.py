from decimal import Decimal

from django.db import models
from django.db.models import Sum


class TransactionType(models.TextChoices):
    TRANSFER = "TRANSFER", "Transfer"
    TOPUP = "TOPUP", "Top-up"
    WITHDRAWAL = "WITHDRAWAL", "Withdrawal"
    REVERSAL = "REVERSAL", "Reversal"


class Transaction(models.Model):
    type = models.CharField(max_length=20, choices=TransactionType.choices)
    reference_transaction = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reversals",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Transaction({self.type}, {self.id})"


class EntryType(models.TextChoices):
    DEBIT = "DEBIT", "Debit"
    CREDIT = "CREDIT", "Credit"


class EntryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"


class LedgerEntry(models.Model):
    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.CASCADE,
        related_name="ledger_entries",
    )
    type = models.CharField(max_length=10, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    status = models.CharField(
        max_length=10,
        choices=EntryStatus.choices,
        default=EntryStatus.CONFIRMED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_entries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["wallet", "status"]),
            models.Index(fields=["transaction"]),
        ]

    def __str__(self):
        return f"LedgerEntry({self.type} {self.amount} {self.status})"


class IdempotencyKey(models.Model):
    key = models.CharField(max_length=255, unique=True)
    response_body = models.JSONField()
    status_code = models.PositiveIntegerField(default=201)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "idempotency_keys"

    def __str__(self):
        return self.key


def calculate_wallet_balance(wallet_id: int) -> Decimal:
    """Sum CONFIRMED credits minus CONFIRMED debits — never a stored balance column."""
    confirmed = LedgerEntry.objects.filter(
        wallet_id=wallet_id,
        status=EntryStatus.CONFIRMED,
    )
    credits = confirmed.filter(type=EntryType.CREDIT).aggregate(
        total=Sum("amount"),
    )["total"] or Decimal("0.00")
    debits = confirmed.filter(type=EntryType.DEBIT).aggregate(
        total=Sum("amount"),
    )["total"] or Decimal("0.00")
    return credits - debits


def calculate_available_balance(wallet_id: int) -> Decimal:
    """Confirmed balance minus PENDING debits (reserved for in-flight withdrawals)."""
    pending_debits = LedgerEntry.objects.filter(
        wallet_id=wallet_id,
        status=EntryStatus.PENDING,
        type=EntryType.DEBIT,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return calculate_wallet_balance(wallet_id) - pending_debits


class PaymentDirection(models.TextChoices):
    TOPUP = "TOPUP", "Top-up"
    WITHDRAWAL = "WITHDRAWAL", "Withdrawal"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class Payment(models.Model):
    external_id = models.CharField(max_length=64, unique=True, db_index=True)
    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    direction = models.CharField(max_length=20, choices=PaymentDirection.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.CASCADE,
        related_name="payment",
    )
    webhook_event_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment({self.external_id}, {self.direction}, {self.status})"


class AuditAction(models.TextChoices):
    REVERSAL_CREATED = "REVERSAL_CREATED", "Reversal created"
    PAYMENT_WEBHOOK = "PAYMENT_WEBHOOK", "Payment webhook processed"
    USER_ROLE_CHANGED = "USER_ROLE_CHANGED", "User role changed"


class AuditLog(models.Model):
    actor = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=40, choices=AuditAction.choices)
    target_type = models.CharField(max_length=40)
    target_id = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]

    def __str__(self):
        return f"AuditLog({self.action}, {self.target_type}:{self.target_id})"
