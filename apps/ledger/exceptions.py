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
