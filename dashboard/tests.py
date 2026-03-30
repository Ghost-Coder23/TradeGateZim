from django.core.cache import cache
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from payments.models import FeeSettings, FeeSettingsAuditLog, Payment
from transactions.models import Transaction


class DashboardRouteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='dash_user',
            password='pass12345',
        )
        self.staff_user = get_user_model().objects.create_user(
            username='dash_admin',
            first_name='Ops',
            last_name='Admin',
            password='pass12345',
            is_staff=True,
            is_superuser=True,
        )
        self.fee_settings = FeeSettings.get_solo()

    def _create_transaction(self, **overrides):
        transaction = Transaction.objects.create(
            user=overrides.pop('user', self.user),
            transaction_type=overrides.pop('transaction_type', 'deposit'),
            platform=overrides.pop('platform', 'binance'),
            amount=overrides.pop('amount', Decimal('10.00')),
            payment_method=overrides.pop('payment_method', 'ecocash'),
            destination_account=overrides.pop('destination_account', 'wallet-1'),
            status=overrides.pop('status', 'pending'),
            rejection_reason=overrides.pop('rejection_reason', ''),
            **overrides,
        )
        payment = Payment.objects.create(
            transaction=transaction,
            payer_number='+263771234567',
            amount=transaction.amount,
            status='awaiting',
        )
        return transaction, payment

    def test_public_and_protected_dashboard_routes(self):
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)
        self.assertEqual(self.client.get(reverse('rates')).status_code, 200)

        dashboard_response = self.client.get(reverse('dashboard'))
        self.assertRedirects(dashboard_response, f"{reverse('login')}?next={reverse('dashboard')}")

        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_admin_panel_requires_staff(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('admin_panel')).status_code, 403)

        self.client.force_login(self.staff_user)
        self.assertEqual(self.client.get(reverse('admin_panel')).status_code, 200)

    def test_non_staff_cannot_run_admin_transaction_actions(self):
        transaction, _payment = self._create_transaction()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('admin_transaction_action', args=[transaction.pk]),
            {'action': 'approve'},
        )

        self.assertEqual(response.status_code, 403)

    def test_staff_can_approve_transaction_from_admin_panel(self):
        transaction, payment = self._create_transaction()
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse('admin_transaction_action', args=[transaction.pk]),
            {'action': 'approve', 'note': 'Funds seen in queue', 'next': reverse('admin_panel')},
        )

        self.assertRedirects(response, reverse('admin_panel'))
        transaction.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(transaction.status, 'completed')
        self.assertEqual(payment.status, 'confirmed')
        self.assertTrue(payment.confirmed)
        self.assertIn('Approved by Ops Admin', transaction.admin_notes)
        self.assertIn('Processed deposit', transaction.admin_notes)

    def test_staff_can_reject_transaction_from_admin_panel(self):
        transaction, payment = self._create_transaction()
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse('admin_transaction_action', args=[transaction.pk]),
            {'action': 'reject', 'note': 'Amount mismatch', 'next': reverse('admin_panel')},
        )

        self.assertRedirects(response, reverse('admin_panel'))
        transaction.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(transaction.status, 'rejected')
        self.assertEqual(transaction.rejection_reason, 'Amount mismatch')
        self.assertEqual(payment.status, 'failed')
        self.assertFalse(payment.confirmed)

    def test_staff_can_retry_rejected_transaction_from_admin_panel(self):
        transaction, payment = self._create_transaction(status='rejected', rejection_reason='Timed out')
        payment.status = 'failed'
        payment.save(update_fields=['status'])
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse('admin_transaction_action', args=[transaction.pk]),
            {'action': 'retry', 'note': 'Retry after operator review', 'next': reverse('admin_panel')},
        )

        self.assertRedirects(response, reverse('admin_panel'))
        transaction.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(transaction.status, 'completed')
        self.assertEqual(transaction.rejection_reason, '')
        self.assertEqual(payment.status, 'confirmed')
        self.assertTrue(payment.confirmed)
        self.assertIn('Retry requested by Ops Admin', transaction.admin_notes)

    def test_staff_can_reconcile_transaction_from_admin_panel(self):
        transaction, payment = self._create_transaction()
        payment.status = 'confirmed'
        payment.confirmed = True
        payment.save(update_fields=['status', 'confirmed'])
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse('admin_transaction_action', args=[transaction.pk]),
            {'action': 'reconcile', 'note': 'Sync status after external update', 'next': reverse('admin_panel')},
        )

        self.assertRedirects(response, reverse('admin_panel'))
        transaction.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(transaction.status, 'processing')
        self.assertEqual(payment.status, 'confirmed')
        self.assertIn('Reconciled by Ops Admin', transaction.admin_notes)

    def test_staff_can_update_fee_settings_from_admin_panel(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(reverse('admin_fee_settings_update'), {
            'deposit_fee_percent': '2.25',
            'withdrawal_fee_percent': '4.50',
        })

        self.assertRedirects(response, reverse('admin_panel'))
        self.fee_settings.refresh_from_db()
        self.assertEqual(self.fee_settings.deposit_fee_percent, Decimal('2.25'))
        self.assertEqual(self.fee_settings.withdrawal_fee_percent, Decimal('4.50'))
        self.assertEqual(FeeSettingsAuditLog.objects.count(), 1)
        audit_entry = FeeSettingsAuditLog.objects.get()
        self.assertEqual(audit_entry.changed_by, self.staff_user)
        self.assertEqual(audit_entry.source, 'admin_panel')

    @override_settings(
        RATE_LIMITS={
            'admin_action_user': {'limit': 1, 'window': 60},
        }
    )
    def test_admin_transaction_actions_are_rate_limited(self):
        transaction_one, _payment_one = self._create_transaction(destination_account='wallet-21')
        transaction_two, _payment_two = self._create_transaction(destination_account='wallet-22')
        self.client.force_login(self.staff_user)

        first_response = self.client.post(
            reverse('admin_transaction_action', args=[transaction_one.pk]),
            {'action': 'approve', 'next': reverse('admin_panel')},
        )
        self.assertEqual(first_response.status_code, 302)

        second_response = self.client.post(
            reverse('admin_transaction_action', args=[transaction_two.pk]),
            {'action': 'approve', 'next': reverse('admin_panel')},
        )
        self.assertEqual(second_response.status_code, 429)
