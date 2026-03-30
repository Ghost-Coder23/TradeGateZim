
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from transactions.models import Transaction
from payments.models import FeeSettings, Payment, ExchangeRate, SystemFloat

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds the database with simulation data'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding database...')

        # Admin user
        admin, _ = User.objects.get_or_create(username='admin', defaults={
            'email': 'admin@tradegate.zw', 'first_name': 'Admin', 'last_name': 'TradeGate',
            'phone': '+263771000000', 'country': 'ZW', 'email_verified': True,
            'is_staff': True, 'is_superuser': True,
        })
        admin.set_password('admin123')
        admin.save()
        self.stdout.write(self.style.SUCCESS('✓ Admin user: admin / admin123'))

        # Test trader
        trader, _ = User.objects.get_or_create(username='trader1', defaults={
            'email': 'trader@example.com', 'first_name': 'Tatenda', 'last_name': 'Moyo',
            'phone': '+263771234567', 'country': 'ZW', 'email_verified': True,
        })
        trader.set_password('trader123')
        trader.save()
        self.stdout.write(self.style.SUCCESS('✓ Trader user: trader1 / trader123'))

        # Sample transactions
        samples = [
            ('deposit', 'binance', 100, 'ecocash', 'pending', '123456789'),
            ('deposit', 'weltrade', 250, 'bank_transfer', 'completed', 'WT-98765'),
            ('withdrawal', 'binance', 75, 'ecocash', 'completed', '987654321'),
            ('deposit', 'exness', 500, 'ecocash', 'processing', 'EX-11111'),
            ('withdrawal', 'weltrade', 150, 'bank_transfer', 'pending', 'WT-22222'),
        ]

        for ttype, platform, amount, method, status, dest in samples:
            tx = Transaction.objects.create(
                user=trader, transaction_type=ttype, platform=platform,
                amount=amount, payment_method=method, status=status,
                destination_account=dest
            )
            Payment.objects.get_or_create(transaction=tx, defaults={
                'payer_number': '+263771234567', 'amount': amount,
                'confirmed': status == 'completed', 'status': 'confirmed' if status == 'completed' else 'awaiting'
            })

        self.stdout.write(self.style.SUCCESS(f'✓ {len(samples)} sample transactions created'))

        # Exchange rates
        fee_settings = FeeSettings.get_solo()
        ExchangeRate.objects.get_or_create(
            currency_pair='USD/USDT',
            defaults={
                'rate': 1.0002,
                'spread_percent': fee_settings.deposit_fee_percent,
                'effective_rate': round(1.0002 * (1 - float(fee_settings.deposit_fee_percent) / 100), 4),
            }
        )
        self.stdout.write(self.style.SUCCESS('✓ Exchange rate seeded'))

        self.stdout.write(
            self.style.SUCCESS(
                f'✓ Fee settings ready (deposit {fee_settings.deposit_fee_percent}%, '
                f'withdrawal {fee_settings.withdrawal_fee_percent}%)'
            )
        )

        # Float pools
        for name, currency, balance, minimum in [
            ('EcoCash Pool', 'USD', 750.00, 200.00),
            ('USDT Pool (Binance)', 'USDT', 1200.00, 300.00),
            ('Bank Pool', 'USD', 500.00, 100.00),
        ]:
            SystemFloat.objects.get_or_create(name=name, defaults={
                'currency': currency, 'balance': balance, 'minimum_threshold': minimum
            })
        self.stdout.write(self.style.SUCCESS('✓ Liquidity pools seeded'))

        self.stdout.write(self.style.SUCCESS('\n✅ Seed complete! Login at /login/'))
        self.stdout.write('   Admin:  admin / admin123')
        self.stdout.write('   Trader: trader1 / trader123')
