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
| `payments` | Mock provider payment records (top-up / withdraw) |
| `audit_logs` | Immutable audit trail for sensitive actions |

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

## Phase 4 — Top-up / Withdraw ✅

- `POST /topups/` and `POST /withdrawals/` with **Idempotency-Key** header (required)
- Mock payment provider assigns `external_id` per payment
- Ledger entries start as **PENDING**; confirmed balance unchanged until webhook
- `POST /webhooks/payments/` with **HMAC-SHA256** verification (`X-Payment-Signature`)
- Webhook `completed` → entry **CONFIRMED**; `failed` → pending entry removed
- Withdrawals reserve funds via PENDING debits (`available_balance` = confirmed − pending debits)

### Top-up / Withdraw API

| Method | Endpoint | Headers | Body |
|--------|----------|---------|------|
| POST | `/topups/` | `Authorization`, `Idempotency-Key` | `wallet_id`, `amount` |
| POST | `/withdrawals/` | `Authorization`, `Idempotency-Key` | `wallet_id`, `amount` |
| POST | `/webhooks/payments/` | `X-Payment-Signature` | `event_id`, `payment_id`, `status` |

### Example top-up + webhook confirm

```powershell
# 1) Initiate top-up (returns external_id, status PENDING)
curl -X POST http://127.0.0.1:8000/topups/ `
  -H "Authorization: Bearer <access_token>" `
  -H "Idempotency-Key: topup-key-001" `
  -H "Content-Type: application/json" `
  -d '{"wallet_id":1,"amount":"500.00"}'

# 2) Mock provider webhook (HMAC over raw JSON body)
# status: "completed" or "failed"
```

### Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `PAYMENT_WEBHOOK_SECRET` | `dev-webhook-secret-change-me` | HMAC secret for payment webhooks |

## Phase 5 — Reversals & Support Tooling ✅

- `POST /reversals/` with **Idempotency-Key** (support/admin only)
- Reverse CONFIRMED **TRANSFER**, **TOPUP**, or **WITHDRAWAL** transactions
- Creates **REVERSAL** transaction linked via `reference_transaction`
- Opposite ledger entries restore balances; no double reversal
- Support lookup APIs for user wallets and pending payments

### Reversal API

| Method | Endpoint | Auth | Body |
|--------|----------|------|------|
| POST | `/reversals/` | Support/Admin + `Idempotency-Key` | `transaction_id` |

### Support API

| Method | Endpoint | Auth | Query params |
|--------|----------|------|--------------|
| GET | `/support/users/` | Support/Admin | `email` |
| GET | `/support/wallets/` | Support/Admin | `email` |
| GET | `/support/payments/` | Support/Admin | `status` (optional) |

### Example reversal

```powershell
curl -X POST http://127.0.0.1:8000/reversals/ `
  -H "Authorization: Bearer <support_access_token>" `
  -H "Idempotency-Key: reversal-key-001" `
  -H "Content-Type: application/json" `
  -d '{"transaction_id":1}'
```

## Phase 6 — Audit Trail, Transaction History & Admin Operations ✅

- `AuditLog` model records reversals, payment webhooks, and role changes
- `GET /transactions/` and `GET /transactions/:id/` for customer transaction history
- Admin-only `/administration/` APIs for user management and audit log review
- Admin can list users and change roles (with audit entry); cannot change own role

### Transaction history API

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/transactions/` | Bearer | List my transactions (via owned wallets) |
| GET | `/transactions/:id/` | Bearer | Transaction detail with ledger entries |

### Administration API

| Method | Endpoint | Auth | Body / Query |
|--------|----------|------|--------------|
| GET | `/administration/users/` | Admin | — |
| PATCH | `/administration/users/:id/role/` | Admin | `role` |
| GET | `/administration/audit-logs/` | Admin | `action`, `actor_email` (optional) |

### Audited actions

| Action | Trigger |
|--------|---------|
| `REVERSAL_CREATED` | Support/admin creates a reversal |
| `PAYMENT_WEBHOOK` | Payment provider webhook processed |
| `USER_ROLE_CHANGED` | Admin changes a user's role |
