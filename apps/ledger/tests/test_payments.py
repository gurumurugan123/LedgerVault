import json
import uuid
from decimal import Decimal

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.ledger.models import (
    EntryStatus,
    EntryType,
    IdempotencyKey,
    LedgerEntry,
    Payment,
    PaymentStatus,
    Transaction,
    TransactionType,
    calculate_available_balance,
    calculate_wallet_balance,
)
from apps.ledger.payment_provider import compute_webhook_signature
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
def other_user(db):
    return User.objects.create_user(
        email="other@example.com",
        password="SecurePass123!",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def auth_client(api_client, customer):
    tokens = issue_tokens(customer)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return api_client


@pytest.fixture
def wallet(customer):
    return Wallet.objects.create(user=customer, name="Main Wallet", currency="INR")


def fund_wallet(wallet, amount):
    tx = Transaction.objects.create(type=TransactionType.TOPUP)
    LedgerEntry.objects.create(
        wallet=wallet,
        type=EntryType.CREDIT,
        amount=amount,
        transaction=tx,
        status=EntryStatus.CONFIRMED,
    )


def topup_request(client, wallet_id, amount, idempotency_key):
    return client.post(
        reverse("topup-create"),
        {"wallet_id": wallet_id, "amount": str(amount)},
        format="json",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )


def withdraw_request(client, wallet_id, amount, idempotency_key):
    return client.post(
        reverse("withdraw-create"),
        {"wallet_id": wallet_id, "amount": str(amount)},
        format="json",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )


def webhook_request(external_id, event_id, payment_status, payload=None):
    client = APIClient()
    body = payload or {
        "event_id": event_id,
        "payment_id": external_id,
        "status": payment_status,
    }
    raw = json.dumps(body).encode()
    signature = compute_webhook_signature(raw, settings.PAYMENT_WEBHOOK_SECRET)
    return client.post(
        reverse("payment-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_X_PAYMENT_SIGNATURE=signature,
    )


@pytest.mark.django_db
class TestTopUpFlow:
    def test_topup_creates_pending_credit_without_changing_balance(self, auth_client, wallet):
        response = topup_request(auth_client, wallet.id, Decimal("250.00"), "topup-key-1")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["type"] == "TOPUP"
        assert response.data["status"] == PaymentStatus.PENDING
        assert response.data["balance"] == "0.00"
        assert calculate_wallet_balance(wallet.id) == Decimal("0.00")

        entry = LedgerEntry.objects.get(transaction_id=response.data["transaction_id"])
        assert entry.status == EntryStatus.PENDING
        assert entry.type == EntryType.CREDIT

    def test_topup_webhook_completed_confirms_balance(self, auth_client, wallet):
        topup = topup_request(auth_client, wallet.id, Decimal("250.00"), "topup-key-2")
        external_id = topup.data["external_id"]

        webhook = webhook_request(external_id, "evt-topup-1", "completed")

        assert webhook.status_code == status.HTTP_200_OK
        assert webhook.data["status"] == PaymentStatus.COMPLETED
        assert webhook.data["balance"] == "250.00"
        assert calculate_wallet_balance(wallet.id) == Decimal("250.00")

    def test_topup_webhook_failed_removes_pending_entry(self, auth_client, wallet):
        topup = topup_request(auth_client, wallet.id, Decimal("100.00"), "topup-key-3")
        external_id = topup.data["external_id"]
        transaction_id = topup.data["transaction_id"]

        webhook = webhook_request(external_id, "evt-topup-fail", "failed")

        assert webhook.status_code == status.HTTP_200_OK
        assert webhook.data["status"] == PaymentStatus.FAILED
        assert calculate_wallet_balance(wallet.id) == Decimal("0.00")
        assert not LedgerEntry.objects.filter(transaction_id=transaction_id).exists()

    def test_topup_requires_idempotency_key(self, auth_client, wallet):
        response = auth_client.post(
            reverse("topup-create"),
            {"wallet_id": wallet.id, "amount": "10.00"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_topup_idempotency_returns_same_response_once(self, auth_client, wallet):
        headers = {"HTTP_IDEMPOTENCY_KEY": "topup-same-key"}
        payload = {"wallet_id": wallet.id, "amount": "50.00"}

        first = auth_client.post(reverse("topup-create"), payload, format="json", **headers)
        second = auth_client.post(reverse("topup-create"), payload, format="json", **headers)

        assert first.status_code == status.HTTP_201_CREATED
        assert second.data == first.data
        assert Payment.objects.filter(wallet=wallet, direction="TOPUP").count() == 1


@pytest.mark.django_db
class TestWithdrawFlow:
    def test_withdraw_creates_pending_debit_and_reserves_available_balance(
        self, auth_client, wallet
    ):
        fund_wallet(wallet, Decimal("500.00"))

        response = withdraw_request(auth_client, wallet.id, Decimal("200.00"), "withdraw-key-1")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == PaymentStatus.PENDING
        assert response.data["balance"] == "500.00"
        assert response.data["available_balance"] == "300.00"
        assert calculate_wallet_balance(wallet.id) == Decimal("500.00")
        assert calculate_available_balance(wallet.id) == Decimal("300.00")

    def test_withdraw_webhook_completed_reduces_balance(self, auth_client, wallet):
        fund_wallet(wallet, Decimal("500.00"))
        withdraw = withdraw_request(auth_client, wallet.id, Decimal("200.00"), "withdraw-key-2")

        webhook = webhook_request(withdraw.data["external_id"], "evt-withdraw-1", "completed")

        assert webhook.status_code == status.HTTP_200_OK
        assert webhook.data["balance"] == "300.00"
        assert calculate_wallet_balance(wallet.id) == Decimal("300.00")

    def test_withdraw_rejects_insufficient_available_balance(self, auth_client, wallet):
        fund_wallet(wallet, Decimal("100.00"))

        response = withdraw_request(auth_client, wallet.id, Decimal("150.00"), "withdraw-key-3")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert calculate_wallet_balance(wallet.id) == Decimal("100.00")

    def test_pending_withdrawal_blocks_second_overdraft(self, auth_client, wallet):
        fund_wallet(wallet, Decimal("100.00"))
        withdraw_request(auth_client, wallet.id, Decimal("80.00"), "withdraw-key-4")

        response = withdraw_request(auth_client, wallet.id, Decimal("30.00"), "withdraw-key-5")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert calculate_available_balance(wallet.id) == Decimal("20.00")


@pytest.mark.django_db
class TestPaymentWebhookSecurity:
    def test_webhook_rejects_invalid_hmac(self, auth_client, wallet):
        topup = topup_request(auth_client, wallet.id, Decimal("50.00"), "topup-webhook-auth")
        body = {
            "event_id": "evt-bad-sig",
            "payment_id": topup.data["external_id"],
            "status": "completed",
        }
        raw = json.dumps(body).encode()
        client = APIClient()

        response = client.post(
            reverse("payment-webhook"),
            data=raw,
            content_type="application/json",
            HTTP_X_PAYMENT_SIGNATURE="invalid-signature",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert calculate_wallet_balance(wallet.id) == Decimal("0.00")

    def test_duplicate_webhook_event_is_idempotent(self, auth_client, wallet):
        topup = topup_request(auth_client, wallet.id, Decimal("75.00"), "topup-webhook-dup")
        external_id = topup.data["external_id"]
        event_id = f"evt-dup-{uuid.uuid4()}"

        first = webhook_request(external_id, event_id, "completed")
        second = webhook_request(external_id, event_id, "completed")

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert first.data == second.data
        assert calculate_wallet_balance(wallet.id) == Decimal("75.00")
        assert Payment.objects.get(external_id=external_id).webhook_event_id == event_id


@pytest.mark.django_db
class TestPaymentAccessControl:
    def test_topup_rejects_foreign_wallet(self, auth_client, other_user):
        foreign_wallet = Wallet.objects.create(user=other_user, name="Foreign", currency="INR")

        response = topup_request(auth_client, foreign_wallet.id, Decimal("10.00"), "topup-denied")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_withdraw_rejects_foreign_wallet(self, auth_client, other_user):
        foreign_wallet = Wallet.objects.create(user=other_user, name="Foreign", currency="INR")

        response = withdraw_request(
            auth_client, foreign_wallet.id, Decimal("10.00"), "withdraw-denied"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
