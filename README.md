# Next Aura Voice Studio (Premium Hardened Edition)

Next.js 16 frontend + FastAPI hardened backend + swappable VoxCPM AI voice cloning inference architecture.

## Product Plans & Quota Rules
- **Free**: 500 words per generation, 2 generations/week, no account required (isolated per-visitor tracking).
- **Weekly**: 25,000 MMK, up to 5,000 words per generation, 6 generations/week, account required (valid for 7 days).
- **Unlimited**: 50,000 MMK, up to 5,000 words per generation, unlimited generations/week, account required.

*Weekly reset happens automatically every Monday at 00:00:00 UTC.*

---

## Architecture Overview

```text
frontend/ (Next.js 16 + React 19 + TypeScript)
  ├── / (Voice studio & script creation)
  └── /admin (Admin portal with audit logging & purchase reviews)
        │
        ▼ (HTTP REST API / Bearer JWT / Secure HttpOnly Cookies)
backend/ (FastAPI + SQLAlchemy 2.0 + Alembic)
  ├── app/
  │   ├── main.py (FastAPI app, lifespan, CORS, middleware)
  │   ├── config.py (Pydantic Settings, environment security & fail-fast checks)
  │   ├── database.py (SQLAlchemy engine, session factory, transaction rollback)
  │   ├── models/ (User, Generation, PurchaseRequest, AdminAuditLog)
  │   ├── schemas/ (Auth, Voice, Purchase, Admin Pydantic v2 schemas)
  │   ├── api/ (deps.py, auth.py, voice.py, purchases.py, admin.py, health.py)
  │   ├── services/ (quota.py, billing.py, audio_validator.py, voxcpm.py, audit.py)
  │   ├── security/ (jwt.py, password.py, rate_limit.py, anonymous.py)
  │   └── middleware/ (request_id.py, security_headers.py, logging_middleware.py)
  ├── migrations/ (Alembic database migrations)
  └── tests/ (Automated test suite)
```

---

## Getting Started

### 1. Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env

# Run database migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000
```

### 2. Running Backend Tests

```bash
cd backend
source .venv/bin/activate
pytest -v
```

### 3. Frontend Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) for the Voice Studio, or [http://localhost:3000/admin](http://localhost:3000/admin) for the Administrator Portal.

---

## Security & Production Configuration

### Environment Variables

| Variable | Description | Required in Prod |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `development`, `production`, or `test` | Yes |
| `SECRET_KEY` | Cryptographic secret for JWT & signatures (min 32 chars) | Yes |
| `ADMIN_EMAIL` | Initial administrator email | Yes |
| `ADMIN_PASSWORD` | Initial administrator password (min 10 chars, non-default) | Yes |
| `DATABASE_URL` | SQLAlchemy connection string (PostgreSQL recommended in prod) | Yes |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed frontend origins (no wildcards) | Yes |
| `REDIS_URL` | Optional Redis URL for distributed multi-worker rate limiting | Optional |
| `VOXCPM_PROVIDER` | `gradio` (HF Space), `mock` (test), or `self_hosted` | No |
| `HF_TOKEN` | Hugging Face token for gated/private spaces | Optional |

### Generating Secure Secrets

```bash
# Generate SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```
