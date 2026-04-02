from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name, default=None):
    value = os.environ.get(name)
    if value is None:
        return list(default or [])
    return [item.strip() for item in value.split(',') if item.strip()]


SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-simulation-key-change-in-production')
DEBUG = env_bool('DJANGO_DEBUG', True)
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', ['*'] if DEBUG else ['localhost', '127.0.0.1'])
CSRF_TRUSTED_ORIGINS = env_list(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    ['https://*.serveousercontent.com'] if DEBUG else [],
)


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Our apps
    'users',
    'transactions',
    'payments',
    'dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'forex_gateway.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'forex_gateway.context_processors.global_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'forex_gateway.wsgi.application'

POSTGRES_DB = os.environ.get('POSTGRES_DB')
if POSTGRES_DB:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': POSTGRES_DB,
            'USER': os.environ.get('POSTGRES_USER', ''),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
            'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

REDIS_URL = os.environ.get('REDIS_URL', '').strip()
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tradegate-zw-cache',
        }
    }

AUTH_USER_MODEL = 'users.CustomUser'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Harare'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── SIMULATION MODE ─────────────────────────────────────────────────────────
# GO LIVE CHECKLIST:
# 1. Implement the live provider stubs in transactions/services.py:
#    - LiveBinanceProvider
#    - LiveEcoCashProvider
# 2. Keep or replace the float accounting comments in transactions/services.py
#    with your real reconciliation flow from Binance, bank, and mobile-money balances.
# 3. Move secrets below into environment variables instead of hardcoding them here.
# 4. Switch the cache backend to Redis so rate limits work across multiple processes.
# 5. Move the database from SQLite to PostgreSQL and set DEBUG = False.
# 6. Only then change SIMULATION_MODE to False.
SIMULATION_MODE = env_bool('SIMULATION_MODE', True)

# STEP 1 TO GO LIVE: Replace with real Binance API keys
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY', 'SIMULATED_KEY')
BINANCE_SECRET_KEY = os.environ.get('BINANCE_SECRET_KEY', 'SIMULATED_SECRET')
BINANCE_TESTNET = env_bool('BINANCE_TESTNET', True)
BINANCE_WEBHOOK_SECRET = os.environ.get('BINANCE_WEBHOOK_SECRET', '')
BINANCE_TRANSFER_ASSET = os.environ.get('BINANCE_TRANSFER_ASSET', 'USDT')
BINANCE_TRANSFER_NETWORK = os.environ.get('BINANCE_TRANSFER_NETWORK', 'TRX')
BINANCE_API_TIMEOUT_SECONDS = int(os.environ.get('BINANCE_API_TIMEOUT_SECONDS', '15'))

# STEP 2 TO GO LIVE: Replace with EcoCash Merchant credentials
ECOCASH_MERCHANT_CODE = os.environ.get('ECOCASH_MERCHANT_CODE', 'SIMULATED')
ECOCASH_MERCHANT_PIN = os.environ.get('ECOCASH_MERCHANT_PIN', 'SIMULATED')
ECOCASH_API_URL = os.environ.get('ECOCASH_API_URL', 'https://api.ecocash.co.zw/v1/')
ECOCASH_WEBHOOK_SECRET = os.environ.get('ECOCASH_WEBHOOK_SECRET', '')
ECOCASH_API_TIMEOUT_SECONDS = int(os.environ.get('ECOCASH_API_TIMEOUT_SECONDS', '15'))

# STEP 3 TO GO LIVE: Configure real email
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
# For production: use smtp or sendgrid
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'smtp.gmail.com'
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = 'your@email.com'
# EMAIL_HOST_PASSWORD = 'your-app-password'

# Platform settings
PLATFORM_NAME = 'TradeGate ZW'
# Fee defaults are used only when the Fee Settings singleton does not exist yet.
# After the first load, staff can change both values from the admin panel or Django Admin.
DEFAULT_DEPOSIT_FEE_PERCENT = 3.0
DEFAULT_WITHDRAWAL_FEE_PERCENT = 3.0
# Legacy fallback kept for older code paths and migration safety.
PLATFORM_FEE_PERCENT = DEFAULT_DEPOSIT_FEE_PERCENT
ECOCASH_NUMBER = '+263 774487666'  # Your business EcoCash number
BANK_NAME = 'CBZ Bank'
BANK_ACCOUNT = '0000000000'
BANK_BRANCH = 'Harare Branch'

# Cache-backed fixed-window rate limits.
# For production, keep the same keys and move the cache backend to Redis.
RATE_LIMITS = {
    'login_ip': {'limit': 5, 'window': 15 * 60},
    'login_username': {'limit': 5, 'window': 15 * 60},
    'register_ip': {'limit': 5, 'window': 60 * 60},
    'transaction_submit_user': {'limit': 10, 'window': 60 * 60},
    'transaction_action_user': {'limit': 20, 'window': 60 * 60},
    'admin_action_user': {'limit': 30, 'window': 60 * 60},
}
