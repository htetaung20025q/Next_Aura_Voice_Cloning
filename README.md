# Next Aura Voice Studio

Next.js frontend + FastAPI backend + Hugging Face VoxCPM-Demo.

## Plans
- Free: 500 words per generation, 2 generations/week, no account required.
- Weekly: 25,000 MMK, up to 5,000 words per generation, 6 generations/week, account required.
- Unlimited: 50,000 MMK, up to 5,000 words per generation, unlimited generations, account required.

Premium purchases are submitted with a payment reference and activated by an admin after verification.

## Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```
Set a strong `SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` before production.

## Frontend
```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```
Open http://localhost:3000

## Admin
Open `/admin`, login using the admin credentials configured in backend `.env`, then approve pending premium purchases.

For real payments, replace the payment-reference flow with the payment provider/API you choose. Never put payment secrets in Next.js client code.
