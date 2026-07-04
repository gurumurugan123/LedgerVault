import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import pytest
from django.db import connections
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
def auth_client(api_client, customer):
    tokens = issue_tokens(customer)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return api_client


@pytest.fixture
def from_wallet(customer):
    return Wallet.objects.create(user=customer, name="From", currency="INR")


@pytest.fixture
def to_wallet(recipient):
    return Wallet.objects.create(user=recipient, name="To", currency="INR")


def fund_wallet(wallet, amount):
    tx = Transaction.objects.create(type=TransactionType.TOPUP)
    LedgerEntry.objects.create(
        wallet=wallet,
        type=EntryType.CREDIT,
        amount=amount,
        transaction=tx,
        status=EntryStatus.CONFIRMED,
    )


def transfer_request(client, from_wallet_id, to_wallet_id, amount, idempotency_key):
    return client.post(
        reverse("transfer-create"),
        {
            "from_wallet_id": from_wallet_id,
            "to_wallet_id": to_wallet_id,
            "amount": str(amount),
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )


@pytest.mark.django_db
class TestTransferSuccess:
    def test_transfer_creates_double_entry_and_updates_balances(
        self, auth_client, from_wallet, to_wallet
    ):
        fund_wallet(from_wallet, Decimal("500.00"))

        response = transfer_request(
            auth_client,
            from_wallet.id,
            to_wallet.id,
            Decimal("150.00"),
            "transfer-key-1",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["transaction_id"]
        assert response.data["amount"] == "150.00"
        assert response.data["from_balance"] == "350.00"
        assert response.data["to_balance"] == "150.00"

        tx = Transaction.objects.get(id=response.data["transaction_id"])
        entries = LedgerEntry.objects.filter(transaction=tx)
        assert entries.count() == 2
        assert entries.filter(wallet=from_wallet, type=EntryType.DEBIT).exists()
        assert entries.filter(wallet=to_wallet, type=EntryType.CREDIT).exists()

    def test_transfer_requires_idempotency_key(self, auth_client, from_wallet, to_wallet):
        fund_wallet(from_wallet, Decimal("100.00"))

        response = auth_client.post(
            reverse("transfer-create"),
            {
                "from_wallet_id": from_wallet.id,
                "to_wallet_id": to_wallet.id,
                "amount": "10.00",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_transfer_rejects_insufficient_balance(self, auth_client, from_wallet, to_wallet):
        fund_wallet(from_wallet, Decimal("50.00"))

        response = transfer_request(
            auth_client,
            from_wallet.id,
            to_wallet.id,
            Decimal("100.00"),
            "transfer-key-insufficient",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert calculate_wallet_balance(from_wallet.id) == Decimal("50.00")


@pytest.mark.django_db
class TestTransferIdempotency:
    def test_duplicate_idempotency_key_moves_money_once(self, auth_client, from_wallet, to_wallet):
        fund_wallet(from_wallet, Decimal("200.00"))
        payload = {
            "from_wallet_id": from_wallet.id,
            "to_wallet_id": to_wallet.id,
            "amount": "75.00",
        }
        headers = {"HTTP_IDEMPOTENCY_KEY": "same-key-123"}

        first = auth_client.post(reverse("transfer-create"), payload, format="json", **headers)
        second = auth_client.post(reverse("transfer-create"), payload, format="json", **headers)

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_201_CREATED
        assert first.data == second.data
        assert calculate_wallet_balance(from_wallet.id) == Decimal("125.00")
        assert calculate_wallet_balance(to_wallet.id) == Decimal("75.00")
        assert IdempotencyKey.objects.filter(key="same-key-123").count() == 1
        assert Transaction.objects.filter(type=TransactionType.TRANSFER).count() == 1


@pytest.mark.django_db(transaction=True)
class TestTransferConcurrency:
    def test_concurrent_transfers_only_one_succeeds_with_insufficient_combined_balance(
        self, customer, recipient, from_wallet, to_wallet
    ):
        fund_wallet(from_wallet, Decimal("100.00"))
        barrier_results = []

        def run_transfer(thread_index):
            connections.close_all()
            client = APIClient()
            tokens = issue_tokens(customer)
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
            return transfer_request(
                client,
                from_wallet.id,
                to_wallet.id,
                Decimal("100.00"),
                f"concurrent-key-{thread_index}",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run_transfer, index) for index in range(2)]
            for future in as_completed(futures):
                barrier_results.append(future.result())

        status_codes = sorted(response.status_code for response in barrier_results)
        assert status_codes == [201, 400]
        assert calculate_wallet_balance(from_wallet.id) == Decimal("0.00")
        assert calculate_wallet_balance(to_wallet.id) == Decimal("100.00")
        assert Transaction.objects.filter(type=TransactionType.TRANSFER).count() == 1

    def test_concurrent_same_idempotency_key_moves_money_once(
        self, customer, from_wallet, to_wallet
    ):
        fund_wallet(from_wallet, Decimal("300.00"))
        shared_key = f"shared-{uuid.uuid4()}"
        results = []

        def run_transfer():
            connections.close_all()
            client = APIClient()
            tokens = issue_tokens(customer)
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
            return transfer_request(
                client,
                from_wallet.id,
                to_wallet.id,
                Decimal("50.00"),
                shared_key,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run_transfer) for _ in range(2)]
            for future in as_completed(futures):
                results.append(future.result())

        success_count = sum(1 for response in results if response.status_code == 201)
        assert success_count == 2
        assert results[0].data == results[1].data
        assert calculate_wallet_balance(from_wallet.id) == Decimal("250.00")
        assert Transaction.objects.filter(type=TransactionType.TRANSFER).count() == 1
