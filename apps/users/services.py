from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken as JWTRefreshToken

from apps.users.models import RefreshToken, User


def issue_tokens(user: User) -> dict:
    """Create JWT pair and persist hashed refresh token in the database."""
    jwt_refresh = JWTRefreshToken.for_user(user)
    access_token = str(jwt_refresh.access_token)
    refresh_token = str(jwt_refresh)

    RefreshToken.objects.create(
        user=user,
        token_hash=RefreshToken.hash_token(refresh_token),
        expires_at=timezone.now() + jwt_refresh.lifetime,
    )

    return {
        "access": access_token,
        "refresh": refresh_token,
    }


def revoke_refresh_token(raw_token: str) -> bool:
    token_hash = RefreshToken.hash_token(raw_token)
    updated = RefreshToken.objects.filter(
        token_hash=token_hash,
        revoked=False,
    ).update(revoked=True)
    return updated > 0


def is_refresh_token_valid(raw_token: str) -> bool:
    token_hash = RefreshToken.hash_token(raw_token)
    try:
        record = RefreshToken.objects.get(token_hash=token_hash)
    except RefreshToken.DoesNotExist:
        return False
    return not record.revoked and not record.is_expired
