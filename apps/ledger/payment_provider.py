import hashlib
import hmac
import uuid

from django.conf import settings


def generate_external_payment_id() -> str:
    """Mock payment provider assigns a unique external reference."""
    return f"pay_{uuid.uuid4().hex}"


def compute_webhook_signature(payload: bytes, secret: str | None = None) -> str:
    key = (secret or settings.PAYMENT_WEBHOOK_SECRET).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify_webhook_signature(payload: bytes, signature: str, secret: str | None = None) -> bool:
    if not signature:
        return False
    expected = compute_webhook_signature(payload, secret=secret)
    return hmac.compare_digest(expected, signature.strip())
