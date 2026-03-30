from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from .models import FeeSettings, FeeSettingsAuditLog


class FeeSettingsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='fee_admin',
            password='pass12345',
        )

    def test_get_solo_returns_single_fee_settings_record(self):
        first = FeeSettings.get_solo()
        second = FeeSettings.get_solo()

        self.assertEqual(first.pk, 1)
        self.assertEqual(second.pk, 1)
        self.assertEqual(FeeSettings.objects.count(), 1)

    def test_get_fee_percent_returns_transaction_specific_fee(self):
        fee_settings = FeeSettings.get_solo()
        fee_settings.deposit_fee_percent = Decimal('2.50')
        fee_settings.withdrawal_fee_percent = Decimal('4.75')
        fee_settings.save()

        self.assertEqual(fee_settings.get_fee_percent('deposit'), Decimal('2.50'))
        self.assertEqual(fee_settings.get_fee_percent('withdrawal'), Decimal('4.75'))

    def test_record_change_creates_audit_entry_only_when_values_change(self):
        fee_settings = FeeSettings.get_solo()

        no_change = fee_settings.record_change(
            previous_deposit_fee_percent=fee_settings.deposit_fee_percent,
            previous_withdrawal_fee_percent=fee_settings.withdrawal_fee_percent,
            actor=self.user,
            source='system',
        )
        self.assertIsNone(no_change)

        previous_deposit = fee_settings.deposit_fee_percent
        previous_withdrawal = fee_settings.withdrawal_fee_percent
        fee_settings.deposit_fee_percent = Decimal('2.25')
        fee_settings.withdrawal_fee_percent = Decimal('4.00')
        fee_settings.save()

        audit_entry = fee_settings.record_change(
            previous_deposit_fee_percent=previous_deposit,
            previous_withdrawal_fee_percent=previous_withdrawal,
            actor=self.user,
            source='system',
            note='Quarterly pricing update',
        )

        self.assertIsNotNone(audit_entry)
        self.assertEqual(FeeSettingsAuditLog.objects.count(), 1)
        self.assertEqual(audit_entry.changed_by, self.user)
        self.assertEqual(audit_entry.previous_deposit_fee_percent, Decimal('3.00'))
        self.assertEqual(audit_entry.new_withdrawal_fee_percent, Decimal('4.00'))
