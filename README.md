# flaskwallet - Adeptech Take-Home Implementation

## Overview
Simple e-wallet slice:
- Users with USD & LBP balances (minor units)
- P2P transfers
- Card authorization webhook (retail & e-commerce)
- Idempotency for webhooks

## Quick start (Postgres)
1. Copy `.env.example` -> `.env` and set DATABASE_URL to your Postgres.
2. Create venv & install:
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
3. Initialize DB & migrations:
   export FLASK_APP=manage.py
   flask db init
   flask db migrate -m "initial"
   flask db upgrade
4. Seed:
   python seed.py
5. Run:
   python manage.py

## Endpoints
- `POST /api/signup` -> body: { email, password, first_name?, last_name? }
- `POST /api/topup` -> body: { user_id, currency (USD|LBP), amount (decimal) }
- `POST /api/transfer` -> body: { from_user_id, to_user_id, currency, amount }
- `POST /api/webhook/authorize` -> partner bank sends payload (see spec). Must include `idempotency_key`.

## Tests
Run tests with pytest:
  pytest -q

## Notes
- Money is stored as integer minor-units (cents).
- Webhook rules:
  - card must exist and be active
  - amount > 0
  - E-commerce: require three_ds == "frictionless" and avs_result == "Y"
  - Idempotency key prevents double-processing
