from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from transactions.models import Transaction

class Payment(models.Model):
    PAYMENT_STATUS = [
        ('awaiting', 'Awaiting Payment'),
        ('received', 'Payment Received'),
        ('confirmed', 'Confirmed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name='payment')
    payer_number = models.CharField(max_length=20, blank=True, help_text="EcoCash number or bank account")
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account = models.CharField(max_length=50, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='awaiting')
    payment_proof = models.TextField(blank=True, help_text="Proof of payment description")
    provider_status = models.CharField(max_length=40, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    provider_message = models.TextField(blank=True)
    provider_payload = models.JSONField(default=dict, blank=True)
    received_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment for {self.transaction.reference_code}"


class ExchangeRate(models.Model):
    """Simulated exchange rates - in production these pull from Binance API"""
    currency_pair = models.CharField(max_length=20)  # e.g. USD/USDT
    rate = models.DecimalField(max_digits=10, decimal_places=4)
    spread_percent = models.DecimalField(max_digits=5, decimal_places=2, default=3.00)
    effective_rate = models.DecimalField(max_digits=10, decimal_places=4)
    is_simulated = models.BooleanField(default=True)
    fetched_at = models.DateTimeField(auto_now=True)
    note = models.CharField(max_length=200, default="SIMULATED - Connect Binance API for live rates")

    def __str__(self):
        return f"{self.currency_pair}: {self.rate} (effective: {self.effective_rate})"


class FeeSettings(models.Model):
    """
    Singleton fee configuration.

    GO LIVE:
    - Keep one row only and update it through staff tools.
    - Changing these values should affect only new transactions.
    - Historical transactions should keep the snapshot stored on Transaction.
    """

    deposit_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('3.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
    )
    withdrawal_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('3.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Fee Settings'
        verbose_name_plural = 'Fee Settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Fees - Deposit: {self.deposit_fee_percent}% | "
            f"Withdrawal: {self.withdrawal_fee_percent}%"
        )

    @classmethod
    def get_solo(cls):
        defaults = {
            'deposit_fee_percent': Decimal(str(getattr(settings, 'DEFAULT_DEPOSIT_FEE_PERCENT', 3.0))),
            'withdrawal_fee_percent': Decimal(str(getattr(settings, 'DEFAULT_WITHDRAWAL_FEE_PERCENT', 3.0))),
        }
        fee_settings, _created = cls.objects.get_or_create(pk=1, defaults=defaults)
        return fee_settings

    def get_fee_percent(self, transaction_type):
        if transaction_type == 'deposit':
            return self.deposit_fee_percent
        if transaction_type == 'withdrawal':
            return self.withdrawal_fee_percent
        return Decimal('0.00')

    def _actor_label(self, actor=None):
        if actor is None:
            return 'system'
        full_name = getattr(actor, 'get_full_name', lambda: '')().strip()
        return full_name or getattr(actor, 'username', str(actor))

    def record_change(
        self,
        *,
        previous_deposit_fee_percent,
        previous_withdrawal_fee_percent,
        actor=None,
        source='system',
        note='',
    ):
        previous_deposit_fee_percent = Decimal(str(previous_deposit_fee_percent))
        previous_withdrawal_fee_percent = Decimal(str(previous_withdrawal_fee_percent))

        if (
            previous_deposit_fee_percent == self.deposit_fee_percent
            and previous_withdrawal_fee_percent == self.withdrawal_fee_percent
        ):
            return None

        return FeeSettingsAuditLog.objects.create(
            fee_settings=self,
            previous_deposit_fee_percent=previous_deposit_fee_percent,
            new_deposit_fee_percent=self.deposit_fee_percent,
            previous_withdrawal_fee_percent=previous_withdrawal_fee_percent,
            new_withdrawal_fee_percent=self.withdrawal_fee_percent,
            changed_by=actor if getattr(actor, 'pk', None) else None,
            changed_by_label=self._actor_label(actor),
            source=source,
            note=(note or '').strip(),
        )


class FeeSettingsAuditLog(models.Model):
    SOURCE_CHOICES = [
        ('admin_panel', 'Admin Panel'),
        ('django_admin', 'Django Admin'),
        ('system', 'System'),
    ]

    fee_settings = models.ForeignKey(FeeSettings, on_delete=models.CASCADE, related_name='audit_logs')
    previous_deposit_fee_percent = models.DecimalField(max_digits=5, decimal_places=2)
    new_deposit_fee_percent = models.DecimalField(max_digits=5, decimal_places=2)
    previous_withdrawal_fee_percent = models.DecimalField(max_digits=5, decimal_places=2)
    new_withdrawal_fee_percent = models.DecimalField(max_digits=5, decimal_places=2)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fee_setting_changes',
    )
    changed_by_label = models.CharField(max_length=150, default='system')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='system')
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Fee Settings Audit Log'
        verbose_name_plural = 'Fee Settings Audit Logs'

    def __str__(self):
        return (
            f"Fee change {self.previous_deposit_fee_percent}%/{self.previous_withdrawal_fee_percent}% -> "
            f"{self.new_deposit_fee_percent}%/{self.new_withdrawal_fee_percent}%"
        )


class SystemFloat(models.Model):
    """Tracks your business liquidity pools - simulated"""
    name = models.CharField(max_length=50, unique=True)  # EcoCash, USDT, Bank
    currency = models.CharField(max_length=10)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    minimum_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=200)
    is_simulated = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    note = models.CharField(max_length=200, default="SIMULATED - Connect real accounts for live balances")

    def __str__(self):
        return f"{self.name}: {self.currency} {self.balance}"

    @property
    def is_low(self):
        return self.balance < self.minimum_threshold


class FloatLedgerEntry(models.Model):
    system_float = models.ForeignKey(SystemFloat, on_delete=models.PROTECT, related_name='ledger_entries')
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='float_ledger_entries',
    )
    delta = models.DecimalField(max_digits=12, decimal_places=2)
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    actor_label = models.CharField(max_length=150, default='system')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Float Ledger Entry'
        verbose_name_plural = 'Float Ledger Entries'

    def __str__(self):
        return f"{self.system_float.name}: {self.delta} ({self.balance_before} -> {self.balance_after})"
