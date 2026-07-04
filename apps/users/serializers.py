from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken as JWTRefreshToken

from apps.users.models import User, UserRole
from apps.users.services import issue_tokens, is_refresh_token_valid, revoke_refresh_token


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            role=UserRole.CUSTOMER,
        )
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email", "").lower()
        password = attrs.get("password")
        user = authenticate(
            request=self.context.get("request"),
            username=email,
            password=password,
        )
        if user is None:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")
        attrs["user"] = user
        return attrs


class RefreshTokenSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate(self, attrs):
        raw_token = attrs["refresh"]
        if not is_refresh_token_valid(raw_token):
            raise serializers.ValidationError("Invalid or revoked refresh token.")
        try:
            jwt_refresh = JWTRefreshToken(raw_token)
        except TokenError as exc:
            raise serializers.ValidationError("Invalid or expired refresh token.") from exc
        attrs["jwt_refresh"] = jwt_refresh
        attrs["raw_token"] = raw_token
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate_refresh(self, value):
        if not revoke_refresh_token(value):
            raise serializers.ValidationError("Refresh token not found or already revoked.")
        return value


class AuthResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        user = obj["user"]
        return {
            "id": user.id,
            "email": user.email,
            "role": user.role,
        }


def build_auth_response(user: User) -> dict:
    tokens = issue_tokens(user)
    return {
        "access": tokens["access"],
        "refresh": tokens["refresh"],
        "user": user,
    }
