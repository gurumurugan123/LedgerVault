import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import RefreshToken, User, UserRole


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="customer@example.com",
        password="SecurePass123!",
        role=UserRole.CUSTOMER,
    )


@pytest.mark.django_db
class TestSignup:
    def test_signup_creates_customer_with_tokens(self, api_client):
        response = api_client.post(
            reverse("auth-signup"),
            {"email": "newuser@example.com", "password": "SecurePass123!"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert "access" in response.data
        assert "refresh" in response.data
        assert response.data["user"]["role"] == UserRole.CUSTOMER

        user = User.objects.get(email="newuser@example.com")
        assert user.role == UserRole.CUSTOMER
        assert RefreshToken.objects.filter(user=user, revoked=False).exists()

    def test_signup_rejects_duplicate_email(self, api_client, user):
        response = api_client.post(
            reverse("auth-signup"),
            {"email": user.email, "password": "SecurePass123!"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestLogin:
    def test_login_returns_tokens(self, api_client, user):
        response = api_client.post(
            reverse("auth-login"),
            {"email": user.email, "password": "SecurePass123!"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data
        assert response.data["user"]["email"] == user.email

    def test_login_rejects_invalid_credentials(self, api_client, user):
        response = api_client.post(
            reverse("auth-login"),
            {"email": user.email, "password": "WrongPassword!"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestRefresh:
    def test_refresh_returns_new_tokens(self, api_client, user):
        login = api_client.post(
            reverse("auth-login"),
            {"email": user.email, "password": "SecurePass123!"},
            format="json",
        )
        refresh = login.data["refresh"]

        response = api_client.post(
            reverse("auth-refresh"),
            {"refresh": refresh},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["access"]
        assert response.data["refresh"]
        assert response.data["refresh"] != refresh

    def test_refresh_rejects_revoked_token(self, api_client, user):
        login = api_client.post(
            reverse("auth-login"),
            {"email": user.email, "password": "SecurePass123!"},
            format="json",
        )
        refresh = login.data["refresh"]
        access = login.data["access"]

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        api_client.post(reverse("auth-logout"), {"refresh": refresh}, format="json")

        response = api_client.post(
            reverse("auth-refresh"),
            {"refresh": refresh},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestLogout:
    def test_logout_revokes_refresh_token(self, api_client, user):
        login = api_client.post(
            reverse("auth-login"),
            {"email": user.email, "password": "SecurePass123!"},
            format="json",
        )
        refresh = login.data["refresh"]
        access = login.data["access"]

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = api_client.post(
            reverse("auth-logout"),
            {"refresh": refresh},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        token_hash = RefreshToken.hash_token(refresh)
        assert RefreshToken.objects.get(token_hash=token_hash).revoked is True

    def test_logout_requires_authentication(self, api_client):
        response = api_client.post(
            reverse("auth-logout"),
            {"refresh": "invalid"},
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
