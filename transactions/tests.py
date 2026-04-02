import json

from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal

from payments.models import FeeSettings, FloatLedgerEntry, Payment, SystemFloat
from .models import ProviderWebhookEvent, Transaction
from .services import (
    LiveBinanceProvider,
    LiveEcoCashProvider,
    SimulationBinanceProvider,
    SimulationEcoCashProvider,
    TransactionProcessor,
)


class TransactionRouteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='tx_user',
            password='pass12345',
        )
        SystemFloat.objects.bulk_create([
            SystemFloat(name='EcoCash Pool', currency='USD', balance=Decimal('750.00'), minimum_threshold=Decimal('200.00')),
            SystemFloat(name='USDT Pool (Binance)', currency='USDT', balance=Decimal('1200.00'), minimum_threshold=Decimal('300.00')),
            SystemFloat(name='Bank Pool', currency='USD', balance=Decimal('500.00'), minimum_threshold=Decimal('100.00')),
        ])
        self.transaction = Transaction.objects.create(
            user=self.user,
            transaction_type='deposit',
            platform='binance',
            amount=Decimal('10.00'),
            payment_method='ecocash',
            destination_account='wallet-1',
        )
        Payment.objects.create(
            transaction=self.transaction,
            payer_number='+263771234567',
            amount=Decimal('10.00'),
        )

    def test_protected_pages_redirect_to_login(self):
        for name in ['deposit', 'withdrawal', 'transaction_list', 'transaction_detail']:
            if name == 'transaction_detail':
                response = self.client.get(reverse(name, args=[self.transaction.pk]))
                expected = f"{reverse('login')}?next={reverse(name, args=[self.transaction.pk])}"
            else:
                response = self.client.get(reverse(name))
                expected = f"{reverse('login')}?next={reverse(name)}"
            self.assertRedirects(response, expected)

    def test_simulate_and_cancel_are_post_only(self):
        self.client.force_login(self.user)

        simulate_get = self.client.get(reverse('simulate_payment', args=[self.transaction.pk]))
        self.assertEqual(simulate_get.status_code, 405)

        cancel_get = self.client.get(reverse('cancel_transaction', args=[self.transaction.pk]))
        self.assertEqual(cancel_get.status_code, 405)

    def test_simulate_payment_post_completes_pending_transaction(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('simulate_payment', args=[self.transaction.pk]))
        self.assertRedirects(response, reverse('transaction_detail', args=[self.transaction.pk]))

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.status, 'completed')

    def test_cancel_transaction_post_rejects_pending_transaction(self):
        self.client.force_login(self.user)
        pending_tx = Transaction.objects.create(
            user=self.user,
            transaction_type='deposit',
            platform='binance',
            amount=Decimal('10.00'),
            payment_method='ecocash',
            destination_account='wallet-2',
        )
        Payment.objects.create(
            transaction=pending_tx,
            payer_number='+263771234568',
            amount=Decimal('10.00'),
        )

        response = self.client.post(reverse('cancel_transaction', args=[pending_tx.pk]))
        self.assertRedirects(response, reverse('transaction_list'))

        pending_tx.refresh_from_db()
        self.assertEqual(pending_tx.status, 'rejected')

    def test_simulate_payment_post_uses_withdrawal_flow_for_withdrawals(self):
        self.client.force_login(self.user)
        withdrawal = Transaction.objects.create(
            user=self.user,
            transaction_type='withdrawal',
            platform='binance',
            amount=Decimal('25.00'),
            payment_method='ecocash',
            destination_account='broker-account-1',
        )
        payment = Payment.objects.create(
            transaction=withdrawal,
            payer_number='+263771234569',
            amount=Decimal('25.00'),
        )

        response = self.client.post(reverse('simulate_payment', args=[withdrawal.pk]))
        self.assertRedirects(response, reverse('transaction_detail', args=[withdrawal.pk]))

        withdrawal.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(withdrawal.status, 'completed')
        self.assertIn('Payout sent via EcoCash', withdrawal.admin_notes)
        self.assertTrue(payment.confirmed)

    def test_simulated_deposit_updates_float_pools(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('simulate_payment', args=[self.transaction.pk]))
        self.assertRedirects(response, reverse('transaction_detail', args=[self.transaction.pk]))

        ecocash_pool = SystemFloat.objects.get(name='EcoCash Pool')
        usdt_pool = SystemFloat.objects.get(name='USDT Pool (Binance)')
        bank_pool = SystemFloat.objects.get(name='Bank Pool')

        self.assertEqual(ecocash_pool.balance, Decimal('760.00'))
        self.assertEqual(usdt_pool.balance, Decimal('1190.30'))
        self.assertEqual(bank_pool.balance, Decimal('500.00'))

    def test_deposit_requires_mobile_number_for_mobile_money_methods(self):
        self.client.force_login(self.user)

        existing_transactions = Transaction.objects.count()
        response = self.client.post(reverse('deposit'), {
            'platform': 'binance',
            'amount': '10.00',
            'payment_method': 'ecocash',
            'destination_account': 'wallet-missing-number',
            'payer_number': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A mobile number is required for this payment method.')
        self.assertEqual(Transaction.objects.count(), existing_transactions)

    def test_withdrawal_requires_bank_details_for_bank_transfer(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('withdrawal'), {
            'platform': 'weltrade',
            'amount': '12.00',
            'payment_method': 'bank_transfer',
            'destination_account': 'broker-bank-1',
            'bank_name': '',
            'bank_account': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bank name is required for bank transfers.')
        self.assertContains(response, 'Bank account is required for bank transfers.')

    def test_bank_transfer_deposit_saves_cleaned_bank_details(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('deposit'), {
            'platform': 'weltrade',
            'amount': '40.00',
            'payment_method': 'bank_transfer',
            'destination_account': 'wallet-bank-1',
            'payer_number': '',
            'bank_name': 'CBZ',
            'bank_account': '00112233',
        })

        transaction = Transaction.objects.exclude(pk=self.transaction.pk).latest('created_at')
        payment = transaction.payment

        self.assertRedirects(response, reverse('transaction_detail', args=[transaction.pk]))
        self.assertEqual(payment.payer_number, '')
        self.assertEqual(payment.bank_name, 'CBZ')
        self.assertEqual(payment.bank_account, '00112233')

    @override_settings(
        RATE_LIMITS={
            'transaction_submit_user': {'limit': 1, 'window': 60},
        }
    )
    def test_deposit_submission_is_rate_limited(self):
        self.client.force_login(self.user)
        first_response = self.client.post(reverse('deposit'), {
            'platform': 'binance',
            'amount': '10.00',
            'payment_method': 'ecocash',
            'destination_account': 'wallet-10',
            'payer_number': '+263771234510',
        })
        self.assertEqual(first_response.status_code, 302)

        second_response = self.client.post(reverse('deposit'), {
            'platform': 'binance',
            'amount': '10.00',
            'payment_method': 'ecocash',
            'destination_account': 'wallet-11',
            'payer_number': '+263771234511',
        })
        self.assertEqual(second_response.status_code, 429)

    @override_settings(
        RATE_LIMITS={
            'transaction_action_user': {'limit': 1, 'window': 60},
        }
    )
    def test_simulate_payment_is_rate_limited(self):
        self.client.force_login(self.user)
        first_response = self.client.post(reverse('simulate_payment', args=[self.transaction.pk]))
        self.assertEqual(first_response.status_code, 302)

        second_transaction = Transaction.objects.create(
            user=self.user,
            transaction_type='deposit',
            platform='binance',
            amount=Decimal('12.00'),
            payment_method='ecocash',
            destination_account='wallet-12',
        )
        Payment.objects.create(
            transaction=second_transaction,
            payer_number='+263771234512',
            amount=Decimal('12.00'),
        )

        second_response = self.client.post(reverse('simulate_payment', args=[second_transaction.pk]))
        self.assertEqual(second_response.status_code, 429)

    def test_binance_webhook_capture_links_transaction(self):
        payload = {
            'type': 'withdrawal.completed',
            'reference_code': self.transaction.reference_code,
            'event_id': 'binance-event-1',
        }

        response = self.client.post(
            reverse('binance_webhook'),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_BINANCE_SIGNATURE='demo-signature',
        )

        self.assertEqual(response.status_code, 202)
        event = ProviderWebhookEvent.objects.get(provider='binance')
        self.assertEqual(event.transaction, self.transaction)
        self.assertEqual(event.processing_status, 'linked')
        self.assertEqual(event.signature_status, 'not_configured')
        self.assertEqual(event.external_event_id, 'binance-event-1')

    def test_ecocash_webhook_rejects_invalid_json(self):
        response = self.client.post(
            reverse('ecocash_webhook'),
            data='not-json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)


class TransactionProcessorTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='processor_user',
            password='pass12345',
        )
        SystemFloat.objects.bulk_create([
            SystemFloat(name='EcoCash Pool', currency='USD', balance=Decimal('750.00'), minimum_threshold=Decimal('200.00')),
            SystemFloat(name='USDT Pool (Binance)', currency='USDT', balance=Decimal('1200.00'), minimum_threshold=Decimal('300.00')),
            SystemFloat(name='Bank Pool', currency='USD', balance=Decimal('500.00'), minimum_threshold=Decimal('100.00')),
        ])
        self.processor = TransactionProcessor()

    def test_process_transaction_dispatches_deposits(self):
        deposit = Transaction.objects.create(
            user=self.user,
            transaction_type='deposit',
            platform='binance',
            amount=Decimal('15.00'),
            payment_method='ecocash',
            destination_account='wallet-3',
        )
        payment = Payment.objects.create(
            transaction=deposit,
            payer_number='+263771234570',
            amount=Decimal('15.00'),
        )

        result = self.processor.process_transaction(deposit)

        deposit.refresh_from_db()
        payment.refresh_from_db()
        self.assertTrue(result['success'])
        self.assertEqual(deposit.status, 'completed')
        self.assertTrue(payment.confirmed)

    def test_process_transaction_dispatches_withdrawals(self):
        withdrawal = Transaction.objects.create(
            user=self.user,
            transaction_type='withdrawal',
            platform='weltrade',
            amount=Decimal('18.00'),
            payment_method='ecocash',
            destination_account='broker-4',
        )
        payment = Payment.objects.create(
            transaction=withdrawal,
            payer_number='+263771234571',
            amount=Decimal('18.00'),
        )

        result = self.processor.process_transaction(withdrawal)

        withdrawal.refresh_from_db()
        payment.refresh_from_db()
        self.assertTrue(result['success'])
        self.assertEqual(withdrawal.status, 'completed')
        self.assertIn('Payout sent via EcoCash', withdrawal.admin_notes)
        self.assertTrue(payment.confirmed)

        ecocash_pool = SystemFloat.objects.get(name='EcoCash Pool')
        bank_pool = SystemFloat.objects.get(name='Bank Pool')
        self.assertEqual(bank_pool.balance, Decimal('518.00'))
        self.assertEqual(ecocash_pool.balance, Decimal('732.54'))

    def test_processor_uses_simulation_providers_by_default(self):
        self.assertIsInstance(self.processor.exchange_provider, SimulationBinanceProvider)
        self.assertIsInstance(self.processor.payout_provider, SimulationEcoCashProvider)

    @override_settings(SIMULATION_MODE=False)
    def test_processor_switches_to_live_provider_stubs_when_simulation_is_disabled(self):
        processor = TransactionProcessor()

        self.assertIsInstance(processor.exchange_provider, LiveBinanceProvider)
        self.assertIsInstance(processor.payout_provider, LiveEcoCashProvider)

    @override_settings(SIMULATION_MODE=False)
    def test_get_current_rates_falls_back_cleanly_when_live_provider_is_not_implemented(self):
        processor = TransactionProcessor()

        rates = processor.get_current_rates()

        self.assertFalse(rates['simulated'])
        self.assertEqual(rates['usdt_rate'], 1.0)
        self.assertIn('Live Binance provider', rates['provider_error'])

    def test_completed_transactions_are_not_processed_twice(self):
        deposit = Transaction.objects.create(
            user=self.user,
            transaction_type='deposit',
            platform='binance',
            amount=Decimal('20.00'),
            payment_method='ecocash',
            destination_account='wallet-4',
        )
        Payment.objects.create(
            transaction=deposit,
            payer_number='+263771234572',
            amount=Decimal('20.00'),
        )

        first_result = self.processor.process_transaction(deposit)
        second_result = self.processor.process_transaction(deposit)

        ecocash_pool = SystemFloat.objects.get(name='EcoCash Pool')
        usdt_pool = SystemFloat.objects.get(name='USDT Pool (Binance)')

        self.assertTrue(first_result['success'])
        self.assertFalse(second_result['success'])
        self.assertEqual(ecocash_pool.balance, Decimal('770.00'))
        self.assertEqual(usdt_pool.balance, Decimal('1180.60'))

    def test_processing_writes_float_ledger_entries(self):
        deposit = Transaction.objects.create(
            user=self.user,
            transaction_type='deposit',
            platform='binance',
            amount=Decimal('15.00'),
            payment_method='ecocash',
            destination_account='wallet-ledger-1',
        )
        Payment.objects.create(
            transaction=deposit,
            payer_number='+263771234573',
            amount=Decimal('15.00'),
        )

        result = self.processor.process_transaction(deposit, actor=self.user)

        entries = list(FloatLedgerEntry.objects.filter(transaction=deposit).order_by('created_at'))

        self.assertTrue(result['success'])
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].system_float.name, 'EcoCash Pool')
        self.assertEqual(entries[0].delta, Decimal('15.00'))
        self.assertEqual(entries[0].actor_label, 'processor_user')
        self.assertEqual(entries[1].system_float.name, 'USDT Pool (Binance)')
        self.assertEqual(entries[1].delta, Decimal('-14.55'))

    def test_processing_records_provider_metadata(self):
        deposit = Transaction.objects.create(
            user=self.user,
            transaction_type='deposit',
            platform='binance',
            amount=Decimal('20.00'),
            payment_method='ecocash',
            destination_account='wallet-provider-meta',
        )
        Payment.objects.create(
            transaction=deposit,
            payer_number='+263771234579',
            amount=Decimal('20.00'),
        )

        result = self.processor.process_transaction(deposit)

        deposit.refresh_from_db()
        self.assertTrue(result['success'])
        self.assertEqual(deposit.provider_status, 'completed')
        self.assertTrue(deposit.provider_reference.startswith('SIM_'))
        self.assertTrue(deposit.provider_payload.get('simulated'))
        self.assertIsNotNone(deposit.provider_last_synced_at)

    @override_settings(SIMULATION_MODE=False)
    def test_live_provider_configuration_summary_reports_missing_settings(self):
        processor = TransactionProcessor()

        summary = processor.exchange_provider.configuration_summary()

        self.assertFalse(summary['configured'])
        self.assertIn('BINANCE_API_KEY', summary['missing_settings'])

    def test_insufficient_liquidity_rolls_back_partial_float_changes(self):
        usdt_pool = SystemFloat.objects.get(name='USDT Pool (Binance)')
        usdt_pool.balance = Decimal('5.00')
        usdt_pool.save(update_fields=['balance'])

        deposit = Transaction.objects.create(
            user=self.user,
            transaction_type='deposit',
            platform='binance',
            amount=Decimal('10.00'),
            payment_method='ecocash',
            destination_account='wallet-low-liquidity',
        )
        Payment.objects.create(
            transaction=deposit,
            payer_number='+263771234574',
            amount=Decimal('10.00'),
        )

        result = self.processor.process_transaction(deposit, actor=self.user)

        deposit.refresh_from_db()
        ecocash_pool = SystemFloat.objects.get(name='EcoCash Pool')
        usdt_pool.refresh_from_db()

        self.assertFalse(result['success'])
        self.assertEqual(deposit.status, 'rejected')
        self.assertIn('Insufficient liquidity', deposit.rejection_reason)
        self.assertEqual(ecocash_pool.balance, Decimal('750.00'))
        self.assertEqual(usdt_pool.balance, Decimal('5.00'))
        self.assertEqual(FloatLedgerEntry.objects.filter(transaction=deposit).count(), 0)


class TransactionFeeSnapshotTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='fee_user',
            password='pass12345',
        )
        self.fee_settings = FeeSettings.get_solo()

    def test_transactions_snapshot_current_fee_percent(self):
        self.fee_settings.deposit_fee_percent = Decimal('2.50')
        self.fee_settings.withdrawal_fee_percent = Decimal('4.75')
        self.fee_settings.save()

        deposit = Transaction.objects.create(
            user=self.user,
            transaction_type='deposit',
            platform='binance',
            amount=Decimal('100.00'),
            payment_method='ecocash',
            destination_account='wallet-5',
        )
        withdrawal = Transaction.objects.create(
            user=self.user,
            transaction_type='withdrawal',
            platform='binance',
            amount=Decimal('100.00'),
            payment_method='ecocash',
            destination_account='wallet-6',
        )

        self.assertEqual(deposit.fee_percent_applied, Decimal('2.50'))
        self.assertEqual(deposit.fee, Decimal('2.50'))
        self.assertEqual(deposit.amount_after_fee, Decimal('97.50'))
        self.assertEqual(withdrawal.fee_percent_applied, Decimal('4.75'))
        self.assertEqual(withdrawal.fee, Decimal('4.75'))
        self.assertEqual(withdrawal.amount_after_fee, Decimal('95.25'))

    def test_fee_changes_only_affect_new_transactions(self):
        self.fee_settings.deposit_fee_percent = Decimal('1.50')
        self.fee_settings.withdrawal_fee_percent = Decimal('3.50')
        self.fee_settings.save()

        first_deposit = Transaction.objects.create(
            user=self.user,
            transaction_type='deposit',
            platform='binance',
            amount=Decimal('50.00'),
            payment_method='ecocash',
            destination_account='wallet-7',
        )

        self.fee_settings.deposit_fee_percent = Decimal('5.00')
        self.fee_settings.withdrawal_fee_percent = Decimal('6.00')
        self.fee_settings.save()

        second_deposit = Transaction.objects.create(
            user=self.user,
            transaction_type='deposit',
            platform='binance',
            amount=Decimal('50.00'),
            payment_method='ecocash',
            destination_account='wallet-8',
        )

        first_deposit.refresh_from_db()
        second_deposit.refresh_from_db()
        self.assertEqual(first_deposit.fee_percent_applied, Decimal('1.50'))
        self.assertEqual(first_deposit.fee, Decimal('0.75'))
        self.assertEqual(second_deposit.fee_percent_applied, Decimal('5.00'))
        self.assertEqual(second_deposit.fee, Decimal('2.50'))
