# LedgerVault

A fintech-style digital wallet backend built on double-entry ledger accounting (Django + PostgreSQL).

## Phase 0 — Project setups ✅

- Python virtual environment (`.venv`)
- Django 5 + Django REST Framework + SimpleJWT
- PostgreSQL via environment variables

## Phase 1 — Users & Auth ✅

- Custom `User` model (email login, roles: customer / support / admin)
- `RefreshToken` model (hashed tokens, revoke on logout)
- JWT auth endpoints
- Role-based permission classes (`IsAdmin`, `IsSupport`, `IsCustomer`)

## Phase 2 — Wallets & Ledger ✅

- `Wallet` model (user-owned, name + currency)
- `Transaction` and `LedgerEntry` models (double-entry foundation)
- Balance **calculated** from CONFIRMED ledger entries (no stored balance column)
- Wallet API with owner-only access

## Phase 3 — Transfers ✅

- `POST /transfers/` with **Idempotency-Key** header (required)
- Double-entry: DEBIT source wallet + CREDIT destination wallet
- Single ACID transaction per transfer
- `SELECT FOR UPDATE` row locking on both wallets (deadlock-safe id ordering)
- `IdempotencyKey` table caches responses for safe retries
- Concurrent transfer safety tested

### Transfer API

| Method | Endpoint | Headers | Body |
|--------|----------|---------|------|
| POST | `/transfers/` | `Authorization`, `Idempotency-Key` | `from_wallet_id`, `to_wallet_id`, `amount` |

### Example transfer

```powershell
curl -X POST http://127.0.0.1:8000/transfers/ `
  -H "Authorization: Bearer <access_token>" `
  -H "Idempotency-Key: unique-key-12345" `
  -H "Content-Type: application/json" `
  -d '{"from_wallet_id":1,"to_wallet_id":2,"amount":"100.00"}'
```

### Transfer response

```json
{
  "transaction_id": 1,
  "type": "TRANSFER",
  "from_wallet_id": 1,
  "to_wallet_id": 2,
  "amount": "100.00",
  "from_balance": "400.00",
  "to_balance": "100.00"
}
```

### Wallet API

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/wallets/` | Bearer | Create wallet for logged-in user |
| GET | `/wallets/` | Bearer | List my wallets |
| GET | `/wallets/:id/balance/` | Bearer | Balance = CONFIRMED credits − debits |
| GET | `/wallets/:id/ledger/` | Bearer | Paginated ledger history |

## Auth API

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/signup/` | Public | Register (role defaults to `customer`) |
| POST | `/auth/login/` | Public | Login, returns access + refresh JWT |
| POST | `/auth/refresh/` | Public | Rotate tokens (old refresh revoked) |
| POST | `/auth/logout/` | Bearer token | Revoke refresh token |

## Database tables

| Table | Purpose |
|-------|---------|
| `users` | User accounts with roles |
| `refresh_tokens` | Hashed refresh token records |
| `wallets` | User wallets |
| `transactions` | TRANSFER, TOPUP, WITHDRAWAL, REVERSAL |
| `ledger_entries` | DEBIT/CREDIT entries per wallet |
| `idempotency_keys` | Cached API responses for safe retries |

## Prerequisites

- Python 3.10+
- PostgreSQL running locally

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Health check: http://127.0.0.1:8000/health/

## Run tests

```powershell
pytest apps/ -v
```

## Next phase

**Phase 4:** Top-up / Withdraw — mock payment provider, webhooks, HMAC verification, PENDING → CONFIRMED flow.
