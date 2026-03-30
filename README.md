# TradeGate Zim 🇿🇼 - Forex Trading Gateway for Zimbabwe

Hey there! I'm building TradeGate Zim to solve Zimbabwe's forex nightmare. 

Multi-currency RTGS/USDC/ZWL madness? EcoCash delays? Black market rates? This platform makes forex simple - deposit local currency, get USDT for Binance trading. Clean dashboard, real-time rates, automated tracking.

## Quick Start (Development)

```bash
pip install django python-decimal
cd forex_gateway
python manage.py migrate
python manage.py seed_data  # Creates test users
python manage.py runserver
```

Open: http://127.0.0.1:8000

### Test Accounts:
```
Super Admin: admin / admin123 (@admin-panel)
Trader: trader1 / trader123
```

## What Users See

| Feature | URL | Description |
|---------|-----|-------------|
| Login/Register | `/login/` `/register/` | Clean auth |
| Dashboard | `/dashboard/` | Balance + quick actions |
| Deposit | `/deposit/` | EcoCash → USDT |
| Withdrawal | `/withdraw/` | USDT → EcoCash |
| Transactions | `/transactions/` | Full history |
| Rates | `/rates/` | Live USD/USDT/ZWG |
| Admin | `/admin-panel/` | Staff tools |

## SIMULATION MODE ACTIVE 

THIS IS DEMO ONLY - All payments \"received instantly\" via Simulate Payment button. No real money moves.

**Going Live Requirements (My TODO):**
- Backend complete (Django + PostgreSQL ready)
- Binance API merchant account
- EcoCash merchant integration 
- SSL + payment gateway certs
- Load testing + Celery automation

**Current Status:** Production-ready code, simulation transactions only. Live launch when APIs approved.

## Architecture 

```
forex_gateway/          # Main Django project
├── users/             # Custom auth + profiles
├── transactions/      # Core business logic 
│   └── services.py    # Sim → Live switch here
├── payments/          # Rates, fees, float tracking
├── dashboard/         # Frontend + admin panel
└── templates/         # Responsive HTML
```

**Key Features:**
- Real-time rate fetching (sim)
- 3% configurable fees (deposits/withdrawals)
- Balance tracking + audit logs
- Responsive design (mobile-first)
- Staff admin dashboard

## Revenue Model
```
User: EcoCash 100 ZWG ($10)
↓ 3% fee
Platform: $0.30 
User receives: 9.7 USDT
```

## Production Deployment (My Next Steps)

1. Database: PostgreSQL + Redis
2. APIs: 
   ```python
   # settings.py - uncomment when ready
   SIMULATION_MODE = False
   BINANCE_API_KEY = env('BINANCE_KEY')
   ECOCASH_MERCHANT_CODE = env('ECOCASH_CODE')
   ```
3. Deploy: Railway/Heroku/DigitalOcean
4. Background: Celery for rate sync + notifications

## Contributing
```
# Development
pip install -r requirements.txt  # Coming soon
python manage.py test
```

Issues? Open one. Zim fintech ideas? DM me!

Live demo when APIs approved. 🇿🇼

Star if this helps Zim traders!

