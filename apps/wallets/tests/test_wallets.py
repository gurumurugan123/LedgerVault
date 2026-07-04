from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.ledger.models import (
    EntryStatus,
    EntryType,
    LedgerEntry,
    Transaction,
    TransactionType,
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


def add_ledger_entry(wallet, entry_type, amount, entry_status=EntryStatus.CONFIRMED):
    transaction = Transaction.objects.create(type=TransactionType.TOPUP)
    return LedgerEntry.objects.create(
        wallet=wallet,
        type=entry_type,
        amount=amount,
        transaction=transaction,
        status=entry_status,
    )


@pytest.mark.django_db
class TestWalletCreate:
    def test_create_wallet(self, auth_client):
        response = auth_client.post(
            reverse("wallet-list-create"),
            {"name": "Savings", "currency": "INR"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Savings"
        assert response.data["currency"] == "INR"

    def test_create_wallet_requires_auth(self, api_client):
        response = api_client.post(
            reverse("wallet-list-create"),
            {"name": "Savings", "currency": "INR"},
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestWalletList:
    def test_list_returns_only_own_wallets(self, auth_client, customer, other_user):
        Wallet.objects.create(user=customer, name="Mine", currency="INR")
        Wallet.objects.create(user=other_user, name="Theirs", currency="INR")

        response = auth_client.get(reverse("wallet-list-create"))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == "Mine"


@pytest.mark.django_db
class TestWalletBalance:
    def test_balance_zero_for_new_wallet(self, auth_client, wallet):
        response = auth_client.get(reverse("wallet-balance", kwargs={"pk": wallet.id}))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["wallet_id"] == wallet.id
        assert response.data["currency"] == "INR"
        assert Decimal(response.data["balance"]) == Decimal("0.00")

    def test_balance_sums_confirmed_entries_only(self, auth_client, wallet):
        add_ledger_entry(wallet, EntryType.CREDIT, Decimal("500.00"))
        add_ledger_entry(wallet, EntryType.DEBIT, Decimal("100.00"))
        add_ledger_entry(
            wallet,
            EntryType.CREDIT,
            Decimal("200.00"),
            entry_status=EntryStatus.PENDING,
        )

        response = auth_client.get(reverse("wallet-balance", kwargs={"pk": wallet.id}))

        assert Decimal(response.data["balance"]) == Decimal("400.00")

    def test_cannot_access_other_users_wallet_balance(self, api_client, other_user, wallet):
        tokens = issue_tokens(other_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        response = api_client.get(reverse("wallet-balance", kwargs={"pk": wallet.id}))

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestWalletLedger:
    def test_ledger_returns_paginated_entries(self, auth_client, wallet):
        add_ledger_entry(wallet, EntryType.CREDIT, Decimal("100.00"))
        add_ledger_entry(wallet, EntryType.DEBIT, Decimal("25.00"))

        response = auth_client.get(reverse("wallet-ledger", kwargs={"pk": wallet.id}))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 2
        assert len(response.data["results"]) == 2
        assert response.data["results"][0]["transaction_type"] == TransactionType.TOPUP

    def test_cannot_access_other_users_wallet_ledger(self, api_client, other_user, wallet):
        tokens = issue_tokens(other_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        response = api_client.get(reverse("wallet-ledger", kwargs={"pk": wallet.id}))

        assert response.status_code == status.HTTP_404_NOT_FOUND
