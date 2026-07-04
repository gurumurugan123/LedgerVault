from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.serializers import (
    AuthResponseSerializer,
    LoginSerializer,
    LogoutSerializer,
    RefreshTokenSerializer,
    SignupSerializer,
    build_auth_response,
)
from apps.users.services import issue_tokens, revoke_refresh_token

User = get_user_model()


class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        response_data = build_auth_response(user)
        return Response(
            AuthResponseSerializer(response_data).data,
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        response_data = build_auth_response(user)
        return Response(AuthResponseSerializer(response_data).data)


class RefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RefreshTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        old_raw_token = serializer.validated_data["raw_token"]
        jwt_refresh = serializer.validated_data["jwt_refresh"]

        revoke_refresh_token(old_raw_token)

        try:
            user = User.objects.get(id=jwt_refresh["user_id"])
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"detail": "User account is disabled."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        tokens = issue_tokens(user)
        response_data = {"access": tokens["access"], "refresh": tokens["refresh"], "user": user}
        return Response(AuthResponseSerializer(response_data).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
