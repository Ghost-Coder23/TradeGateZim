from decimal import Decimal, ROUND_HALF_UP
from django.apps import apps
from django.db import models
from django.conf import settings
import uuid
import random
import string


def generate_reference():
    chars = string.ascii_uppercase + string.digits
    return 'TXN-' + ''.join(random.choices(chars, k=10))


class Transaction(models.Model):
    TYPE_CHOICES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
    ]
    PLATFORM_CHOICES = [
        ('binance', 'Binance'),
        ('weltrade', 'Weltrade'),
        ('exness', 'Exness'),
        ('xm', 'XM'),
        ('other', 'Other Broker'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('ecocash', 'EcoCash'),
        ('bank_transfer', 'Bank Transfer'),
        ('innbucks', 'InnBucks'),
        ('onemoney', 'OneMoney'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    fee_percent_applied = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_after_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    destination_account = models.CharField(max_length=200, help_text="Wallet address or broker account ID")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reference_code = models.CharField(max_length=20, unique=True, default=generate_reference)
    admin_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference_code} - {self.user} - ${self.amount}"

    def _resolve_fee_percent(self):
        if self.fee_percent_applied is not None:
            return Decimal(str(self.fee_percent_applied))

        if not self.transaction_type:
            return Decimal('0.00')

        try:
            FeeSettings = apps.get_model('payments', 'FeeSettings')
            fee_settings = FeeSettings.get_solo()
            fee_percent = fee_settings.get_fee_percent(self.transaction_type)
        except Exception:
            default_key = (
                'DEFAULT_DEPOSIT_FEE_PERCENT'
                if self.transaction_type == 'deposit'
                else 'DEFAULT_WITHDRAWAL_FEE_PERCENT'
            )
            fee_percent = Decimal(str(getattr(settings, default_key, 3.0)))

        self.fee_percent_applied = fee_percent
        return fee_percent

    def save(self, *args, **kwargs):
        # Snapshot the fee percent when the transaction is first created.
        # GO LIVE: do not recalculate historical transactions from the current fee settings.
        if self.amount:
            amount = Decimal(str(self.amount))
            fee_percent = self._resolve_fee_percent()
            fee = (amount * fee_percent / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            self.fee = fee
            self.amount_after_fee = (amount - fee).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    @property
    def status_color(self):
        colors = {
            'pending': 'warning',
            'processing': 'info',
            'completed': 'success',
            'rejected': 'danger',
        }
        return colors.get(self.status, 'secondary')
