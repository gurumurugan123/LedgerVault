from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.ledger.models import AuditAction, AuditLog, Transaction, TransactionType
from apps.ledger.tests.test_payments import fund_wallet, topup_request, webhook_request
from apps.ledger.tests.test_reversals import reversal_request
from apps.ledger.tests.test_transfers import transfer_request
from apps.users.models import User, UserRole
from apps.users.services import issue_tokens
from apps.wallets.models import Wallet


@pytest.fixture
def customer(db):
    return User.objects.create_user(
        email="customer@example.com",
        password="SecurePass123!",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@example.com",
        password="SecurePass123!",
        role=UserRole.ADMIN,
    )


@pytest.fixture
def support_user(db):
    return User.objects.create_user(
        email="support@example.com",
        password="SecurePass123!",
        role=UserRole.SUPPORT,
    )


@pytest.fixture
def customer_client(customer):
    client = APIClient()
    tokens = issue_tokens(customer)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    tokens = issue_tokens(admin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


@pytest.fixture
def support_client(support_user):
    client = APIClient()
    tokens = issue_tokens(support_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


@pytest.fixture
def wallet(customer):
    return Wallet.objects.create(user=customer, name="Main", currency="INR")


@pytest.mark.django_db
class TestTransactionHistory:
    def test_customer_can_list_own_transactions(self, customer_client, wallet):
        fund_wallet(wallet, Decimal("100.00"))

        response = customer_client.get(reverse("transaction-list"))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["type"] == TransactionType.TOPUP
        assert len(response.data[0]["entries"]) == 1

    def test_customer_can_view_own_transaction_detail(self, customer_client, wallet):
        fund_wallet(wallet, Decimal("50.00"))
        transaction_id = customer_client.get(reverse("transaction-list")).data[0]["id"]

        response = customer_client.get(reverse("transaction-detail", kwargs={"pk": transaction_id}))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == transaction_id

    def test_customer_cannot_view_other_users_transaction(self, customer_client, admin_user):
        other_wallet = Wallet.objects.create(user=admin_user, name="Admin Wallet", currency="INR")
        fund_wallet(other_wallet, Decimal("25.00"))
        other_tx = Transaction.objects.filter(entries__wallet=other_wallet).first()

        response = customer_client.get(reverse("transaction-detail", kwargs={"pk": other_tx.id}))

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestAdministrationUsers:
    def test_admin_can_list_users(self, admin_client, customer):
        response = admin_client.get(reverse("administration-user-list"))

        assert response.status_code == status.HTTP_200_OK
        emails = {row["email"] for row in response.data}
        assert customer.email in emails

    def test_admin_can_change_user_role(self, admin_client, customer):
        response = admin_client.patch(
            reverse("administration-user-role", kwargs={"pk": customer.id}),
            {"role": UserRole.SUPPORT},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["role"] == UserRole.SUPPORT
        customer.refresh_from_db()
        assert customer.role == UserRole.SUPPORT

        audit = AuditLog.objects.get(action=AuditAction.USER_ROLE_CHANGED, target_id=str(customer.id))
        assert audit.metadata["new_role"] == UserRole.SUPPORT

    def test_admin_cannot_change_own_role(self, admin_client, admin_user):
        response = admin_client.patch(
            reverse("administration-user-role", kwargs={"pk": admin_user.id}),
            {"role": UserRole.SUPPORT},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_customer_cannot_access_administration_users(self, customer_client):
        response = customer_client.get(reverse("administration-user-list"))

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAuditLogs:
    def test_reversal_creates_audit_log(self, support_client, customer_client, wallet):
        recipient = User.objects.create_user(
            email="recipient@example.com",
            password="SecurePass123!",
            role=UserRole.CUSTOMER,
        )
        to_wallet = Wallet.objects.create(user=recipient, name="To", currency="INR")
        fund_wallet(wallet, Decimal("200.00"))
        transfer = transfer_request(
            customer_client, wallet.id, to_wallet.id, Decimal("75.00"), "audit-transfer"
        )

        reversal_request(support_client, transfer.data["transaction_id"], "audit-reversal")

        audit = AuditLog.objects.get(action=AuditAction.REVERSAL_CREATED)
        assert audit.actor.email == "support@example.com"
        assert audit.target_id == str(transfer.data["transaction_id"])

    def test_payment_webhook_creates_audit_log(self, customer_client, wallet):
        topup = topup_request(customer_client, wallet.id, Decimal("100.00"), "audit-topup")
        webhook_request(topup.data["external_id"], "evt-audit-webhook", "completed")

        audit = AuditLog.objects.get(action=AuditAction.PAYMENT_WEBHOOK)
        assert audit.actor is None
        assert audit.target_id == topup.data["external_id"]

    def test_admin_can_list_audit_logs(self, admin_client, customer):
        AuditLog.objects.create(
            action=AuditAction.USER_ROLE_CHANGED,
            target_type="user",
            target_id=str(customer.id),
            metadata={"email": customer.email},
        )

        response = admin_client.get(reverse("administration-audit-log-list"))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_admin_can_filter_audit_logs_by_action(self, admin_client):
        AuditLog.objects.create(
            action=AuditAction.PAYMENT_WEBHOOK,
            target_type="payment",
            target_id="pay_test",
            metadata={},
        )

        response = admin_client.get(
            reverse("administration-audit-log-list"),
            {"action": AuditAction.PAYMENT_WEBHOOK},
        )

        assert response.status_code == status.HTTP_200_OK
        assert all(row["action"] == AuditAction.PAYMENT_WEBHOOK for row in response.data)
