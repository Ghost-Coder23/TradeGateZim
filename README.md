# TradeGate ZW — Django Fintech Platform

## Quick Start

```bash
cd forex_gateway
pip install django
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

Then open: http://127.0.0.1:8000

## Login Credentials (after seed_data)
- Admin:  admin / admin123
- Trader: trader1 / trader123

## Pages
| URL | Page |
|-----|------|
| /login/ | Login |
| /register/ | Register |
| /dashboard/ | User Dashboard |
| /deposit/ | New Deposit |
| /withdraw/ | New Withdrawal |
| /transactions/ | Transaction History |
| /rates/ | Exchange Rates |
| /admin-panel/ | Admin Panel (staff only) |
| /admin/ | Django Admin (staff only) |

## Simulation Mode
All transactions are simulated. On any pending transaction, click
**Simulate Payment** to instantly process it without real money.

## Going Live (Steps)

### Step 1 — Binance API
```python
# In settings.py
BINANCE_API_KEY = 'your-real-key'
BINANCE_SECRET_KEY = 'your-real-secret'
BINANCE_TESTNET = False

# Install: pip install python-binance
# In transactions/services.py, uncomment the production code blocks
```

### Step 2 — EcoCash Merchant API
```python
# Apply at: https://www.cassavafintech.com
# Then in settings.py:
ECOCASH_MERCHANT_CODE = 'your-merchant-code'
ECOCASH_MERCHANT_PIN = 'your-merchant-pin'
# Uncomment production code in services.py
```

### Step 3 — Disable Simulation
```python
# In settings.py:
SIMULATION_MODE = False

# Switch database to PostgreSQL:
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'tradegate_db',
        'USER': 'your_user',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
    }
}
```

### Step 4 — Phase 2 Automation (Celery)
```bash
pip install celery redis
# Add background tasks for auto-rate-fetching and Binance monitoring
```

## Project Structure
```
forex_gateway/
├── users/          # Auth, registration, profiles
├── transactions/   # Deposits, withdrawals, services layer
│   └── services.py # ← Simulation layer + production code comments
├── payments/       # Payment records, exchange rates, float tracking
├── dashboard/      # User dashboard + admin panel
└── templates/      # All HTML templates
```

## Revenue Model
- 3% fee on every transaction (configurable in settings.py → PLATFORM_FEE_PERCENT)
- Example: User sends $100 → receives $97 USDT → you earn $3
