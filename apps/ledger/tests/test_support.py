from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.ledger.models import PaymentStatus
from apps.ledger.tests.test_payments import topup_request
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
def wallet(customer):
    return Wallet.objects.create(user=customer, name="Main", currency="INR")


@pytest.mark.django_db
class TestSupportUserLookup:
    def test_support_can_lookup_user_by_email(self, support_client, customer, wallet):
        response = support_client.get(
            reverse("support-user-lookup"),
            {"email": customer.email},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == customer.email
        assert response.data["wallet_count"] == 1

    def test_customer_cannot_access_support_user_lookup(self, auth_client, customer):
        response = auth_client.get(
            reverse("support-user-lookup"),
            {"email": customer.email},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_support_user_lookup_requires_email(self, support_client):
        response = support_client.get(reverse("support-user-lookup"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestSupportWalletLookup:
    def test_support_can_list_user_wallets_with_balances(
        self, support_client, customer, wallet
    ):
        response = support_client.get(
            reverse("support-wallet-lookup"),
            {"email": customer.email},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == customer.email
        assert len(response.data["wallets"]) == 1
        assert response.data["wallets"][0]["balance"] == "0.00"


@pytest.mark.django_db
class TestSupportPaymentList:
    def test_support_can_list_pending_payments(
        self, support_client, auth_client, wallet
    ):
        topup_request(auth_client, wallet.id, Decimal("100.00"), "support-pending-topup")

        response = support_client.get(
            reverse("support-payment-list"),
            {"status": PaymentStatus.PENDING},
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["status"] == PaymentStatus.PENDING
        assert response.data[0]["user_email"] == wallet.user.email

    def test_support_payment_list_rejects_invalid_status(self, support_client):
        response = support_client.get(
            reverse("support-payment-list"),
            {"status": "INVALID"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_customer_cannot_list_support_payments(self, auth_client):
        response = auth_client.get(reverse("support-payment-list"))

        assert response.status_code == status.HTTP_403_FORBIDDEN
