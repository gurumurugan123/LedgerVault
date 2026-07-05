import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.ledger.models import (
    EntryStatus,
    EntryType,
    IdempotencyKey,
    LedgerEntry,
    Transaction,
    TransactionType,
    calculate_wallet_balance,
)
from apps.ledger.tests.test_payments import fund_wallet, topup_request, webhook_request
from apps.ledger.tests.test_transfers import transfer_request
from apps.users.models import User, UserRole
from apps.users.services import issue_tokens
from apps.wallets.models import Wallet


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def customer(db):
    return User.objects.create_user(
        email="customer@example.com",
        password="SecurePass123!",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def recipient(db):
    return User.objects.create_user(
        email="recipient@example.com",
        password="SecurePass123!",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def support_user(db):
    return User.objects.create_user(
        email="support@example.com",
        password="SecurePass123!",
        role=UserRole.SUPPORT,
    )


@pytest.fixture
def support_client(support_user):
    client = APIClient()
    tokens = issue_tokens(support_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


@pytest.fixture
def auth_client(customer):
    client = APIClient()
    tokens = issue_tokens(customer)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


@pytest.fixture
def from_wallet(customer):
    return Wallet.objects.create(user=customer, name="From", currency="INR")


@pytest.fixture
def to_wallet(recipient):
    return Wallet.objects.create(user=recipient, name="To", currency="INR")


def reversal_request(client, transaction_id, idempotency_key):
    return client.post(
        reverse("reversal-create"),
        {"transaction_id": transaction_id},
        format="json",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )


@pytest.mark.django_db
class TestReversalTransfer:
    def test_reversal_restores_transfer_balances(
        self, support_client, auth_client, from_wallet, to_wallet
    ):
        fund_wallet(from_wallet, Decimal("500.00"))
        transfer = transfer_request(
            auth_client, from_wallet.id, to_wallet.id, Decimal("150.00"), "transfer-for-reversal"
        )
        transaction_id = transfer.data["transaction_id"]

        response = reversal_request(support_client, transaction_id, "reversal-transfer-1")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["original_transaction_id"] == transaction_id
        assert response.data["type"] == TransactionType.REVERSAL
        assert calculate_wallet_balance(from_wallet.id) == Decimal("500.00")
        assert calculate_wallet_balance(to_wallet.id) == Decimal("0.00")

    def test_reversal_rejects_already_reversed_transaction(
        self, support_client, auth_client, from_wallet, to_wallet
    ):
        fund_wallet(from_wallet, Decimal("200.00"))
        transfer = transfer_request(
            auth_client, from_wallet.id, to_wallet.id, Decimal("50.00"), "transfer-double-reverse"
        )
        transaction_id = transfer.data["transaction_id"]

        first = reversal_request(support_client, transaction_id, "reversal-first")
        second = reversal_request(support_client, transaction_id, "reversal-second")

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_400_BAD_REQUEST

    def test_reversal_rejects_insufficient_balance_on_recipient_wallet(
        self, support_client, auth_client, recipient, from_wallet, to_wallet
    ):
        fund_wallet(from_wallet, Decimal("100.00"))
        transfer = transfer_request(
            auth_client, from_wallet.id, to_wallet.id, Decimal("100.00"), "transfer-spend-all"
        )
        transaction_id = transfer.data["transaction_id"]

        recipient_client = APIClient()
        recipient_tokens = issue_tokens(recipient)
        recipient_client.credentials(HTTP_AUTHORIZATION=f"Bearer {recipient_tokens['access']}")
        transfer_request(
            recipient_client,
            to_wallet.id,
            from_wallet.id,
            Decimal("100.00"),
            "transfer-spend-received",
        )

        response = reversal_request(support_client, transaction_id, "reversal-no-funds")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestReversalTopUp:
    def test_reversal_restores_topup_balance(self, support_client, auth_client, from_wallet):
        topup = topup_request(auth_client, from_wallet.id, Decimal("300.00"), "topup-for-reversal")
        webhook_request(topup.data["external_id"], "evt-topup-rev", "completed")
        transaction_id = topup.data["transaction_id"]
        assert calculate_wallet_balance(from_wallet.id) == Decimal("300.00")

        response = reversal_request(support_client, transaction_id, "reversal-topup-1")

        assert response.status_code == status.HTTP_201_CREATED
        assert calculate_wallet_balance(from_wallet.id) == Decimal("0.00")


@pytest.mark.django_db
class TestReversalPermissions:
    def test_customer_cannot_reverse(self, auth_client, from_wallet):
        fund_wallet(from_wallet, Decimal("100.00"))
        tx = Transaction.objects.create(type=TransactionType.TOPUP)
        LedgerEntry.objects.create(
            wallet=from_wallet,
            type=EntryType.CREDIT,
            amount=Decimal("100.00"),
            transaction=tx,
            status=EntryStatus.CONFIRMED,
        )

        response = reversal_request(auth_client, tx.id, "reversal-customer-denied")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_reversal_idempotency(self, support_client, from_wallet):
        fund_wallet(from_wallet, Decimal("100.00"))
        tx = Transaction.objects.create(type=TransactionType.TOPUP)
        LedgerEntry.objects.create(
            wallet=from_wallet,
            type=EntryType.CREDIT,
            amount=Decimal("100.00"),
            transaction=tx,
            status=EntryStatus.CONFIRMED,
        )
        headers = {"HTTP_IDEMPOTENCY_KEY": "reversal-idem-key"}

        first = support_client.post(
            reverse("reversal-create"),
            {"transaction_id": tx.id},
            format="json",
            **headers,
        )
        second = support_client.post(
            reverse("reversal-create"),
            {"transaction_id": tx.id},
            format="json",
            **headers,
        )

        assert first.status_code == status.HTTP_201_CREATED
        assert second.data == first.data
        assert IdempotencyKey.objects.filter(key="reversal-idem-key").count() == 1


@pytest.mark.django_db
class TestReversalValidation:
    def test_cannot_reverse_pending_topup(self, support_client, auth_client, from_wallet):
        topup = topup_request(auth_client, from_wallet.id, Decimal("100.00"), "topup-pending-rev")

        response = reversal_request(support_client, topup.data["transaction_id"], "reversal-pending")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_reverse_nonexistent_transaction(self, support_client):
        response = reversal_request(support_client, 99999, "reversal-missing")

        assert response.status_code == status.HTTP_404_NOT_FOUND
