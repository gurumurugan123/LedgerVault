class TransferError(Exception):
    """Base error for transfer operations."""


class InsufficientBalanceError(TransferError):
    """Raised when the source wallet has insufficient confirmed balance."""


class WalletNotFoundError(TransferError):
    """Raised when a wallet id does not exist."""


class WalletAccessDeniedError(TransferError):
    """Raised when the user does not own the source wallet."""


class InvalidTransferError(TransferError):
    """Raised for invalid transfer parameters."""


class PaymentError(Exception):
    """Base error for payment operations."""


class PaymentNotFoundError(PaymentError):
    """Raised when a payment id does not exist."""


class InvalidPaymentError(PaymentError):
    """Raised for invalid payment parameters or webhook payloads."""


class WebhookSignatureError(PaymentError):
    """Raised when webhook HMAC verification fails."""
