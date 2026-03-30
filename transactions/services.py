"""
Transaction services and provider selection.

The important split here is:
- provider classes handle exchange / payout integrations
- TransactionProcessor handles transaction state changes and admin workflows

That lets simulation mode and future live providers share the same contract.
"""

import random
import time
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone


class ProviderConfigurationError(RuntimeError):
    """Raised when a live provider has been selected but is not configured yet."""


class InsufficientFloatError(RuntimeError):
    """Raised when a float pool does not have enough liquidity for a movement."""


class BaseExchangeProvider:
    provider_name = 'exchange'
    simulated = False

    def get_usdt_balance(self):
        raise NotImplementedError

    def send_usdt(self, address, amount, transaction_ref):
        raise NotImplementedError

    def get_current_rate(self, pair='USDTUSDT'):
        raise NotImplementedError

    def check_incoming_payment(self, address, expected_amount):
        raise NotImplementedError


class SimulationBinanceProvider(BaseExchangeProvider):
    provider_name = 'binance'
    simulated = True

    def get_usdt_balance(self):
        return 1250.00

    def send_usdt(self, address, amount, transaction_ref):
        time.sleep(0.5)
        fake_hash = f"SIM_{transaction_ref}_{random.randint(100000, 999999)}"
        return {
            'success': True,
            'tx_hash': fake_hash,
            'amount': amount,
            'address': address,
            'simulated': True,
            'note': 'SIMULATED - No real funds moved',
        }

    def get_current_rate(self, pair='USDTUSDT'):
        base = 1.0
        variation = random.uniform(-0.002, 0.002)
        return round(base + variation, 4)

    def check_incoming_payment(self, address, expected_amount):
        return {
            'received': True,
            'amount': expected_amount,
            'confirmations': 12,
            'simulated': True,
        }


class LiveBinanceProvider(BaseExchangeProvider):
    provider_name = 'binance'
    simulated = False

    def _not_configured(self, capability):
        raise ProviderConfigurationError(
            f"Live Binance provider cannot {capability} yet. "
            "Replace the provider stub in transactions/services.py with real Binance API calls."
        )

    def get_usdt_balance(self):
        self._not_configured('fetch balances')

    def send_usdt(self, address, amount, transaction_ref):
        self._not_configured('send USDT')

    def get_current_rate(self, pair='USDTUSDT'):
        self._not_configured('fetch exchange rates')

    def check_incoming_payment(self, address, expected_amount):
        self._not_configured('check incoming payments')


class BasePayoutProvider:
    provider_name = 'mobile_money'
    simulated = False

    def verify_payment(self, phone_number, amount, reference):
        raise NotImplementedError

    def send_payment(self, phone_number, amount, reference, reason):
        raise NotImplementedError


class SimulationEcoCashProvider(BasePayoutProvider):
    provider_name = 'ecocash'
    simulated = True

    def verify_payment(self, phone_number, amount, reference):
        return {
            'verified': True,
            'phone': phone_number,
            'amount': amount,
            'reference': reference,
            'simulated': True,
            'note': 'SIMULATED - In production, pings EcoCash API',
        }

    def send_payment(self, phone_number, amount, reference, reason):
        return {
            'success': True,
            'phone': phone_number,
            'amount': amount,
            'reference': reference,
            'simulated': True,
            'note': 'SIMULATED - No real EcoCash sent',
        }


class LiveEcoCashProvider(BasePayoutProvider):
    provider_name = 'ecocash'
    simulated = False

    def _not_configured(self, capability):
        raise ProviderConfigurationError(
            f"Live EcoCash provider cannot {capability} yet. "
            "Replace the provider stub in transactions/services.py with real EcoCash API calls."
        )

    def verify_payment(self, phone_number, amount, reference):
        self._not_configured('verify payments')

    def send_payment(self, phone_number, amount, reference, reason):
        self._not_configured('send payouts')


def get_exchange_provider():
    if settings.SIMULATION_MODE:
        return SimulationBinanceProvider()
    return LiveBinanceProvider()


def get_payout_provider():
    if settings.SIMULATION_MODE:
        return SimulationEcoCashProvider()
    return LiveEcoCashProvider()


SIMULATED_FLOAT_SPECS = {
    'EcoCash Pool': {
        'currency': 'USD',
        'opening_balance': Decimal('750.00'),
        'minimum_threshold': Decimal('200.00'),
    },
    'USDT Pool (Binance)': {
        'currency': 'USDT',
        'opening_balance': Decimal('1200.00'),
        'minimum_threshold': Decimal('300.00'),
    },
    'Bank Pool': {
        'currency': 'USD',
        'opening_balance': Decimal('500.00'),
        'minimum_threshold': Decimal('100.00'),
    },
}


class TransactionProcessor:
    """Coordinates transaction state and delegates external work to provider classes."""

    def __init__(self, exchange_provider=None, payout_provider=None):
        self.exchange_provider = exchange_provider or get_exchange_provider()
        self.payout_provider = payout_provider or get_payout_provider()
        # Keep legacy attribute names so the rest of the project still works.
        self.binance = self.exchange_provider
        self.ecocash = self.payout_provider

    def _actor_label(self, actor=None):
        if actor is None:
            return 'system'
        full_name = getattr(actor, 'get_full_name', lambda: '')().strip()
        return full_name or getattr(actor, 'username', str(actor))

    def _append_admin_note(self, transaction, note):
        note = (note or '').strip()
        if not note:
            return
        timestamp = timezone.localtime().strftime('%Y-%m-%d %H:%M')
        entry = f"[{timestamp}] {note}"
        existing = (transaction.admin_notes or '').strip()
        transaction.admin_notes = f"{existing}\n{entry}" if existing else entry

    def _update_payment_status(self, payment, *, status=None, confirmed=None, confirmed_at=None):
        if not payment:
            return

        if status is not None:
            payment.status = status
        if confirmed is not None:
            payment.confirmed = confirmed
        payment.confirmed_at = confirmed_at
        payment.save()

    def _pool_name_for_payment_method(self, payment_method):
        if payment_method == 'bank_transfer':
            return 'Bank Pool'
        if payment_method in {'ecocash', 'innbucks', 'onemoney'}:
            return 'EcoCash Pool'
        return 'Bank Pool'

    def _transaction_pk(self, transaction):
        return getattr(transaction, 'pk', transaction)

    def _get_locked_transaction(self, transaction):
        from transactions.models import Transaction

        return Transaction.objects.select_for_update().select_related('payment', 'user').get(
            pk=self._transaction_pk(transaction)
        )

    def _pool_name_for_platform(self, platform):
        if platform == 'binance':
            return 'USDT Pool (Binance)'
        return 'Bank Pool'

    def _get_or_create_float_pool(self, pool_name):
        """
        Simulation float storage.

        GO LIVE:
        1. Keep SystemFloat as an internal ledger or cached balance snapshot.
        2. Replace auto-created defaults with real account onboarding data.
        3. Reconcile these balances against live provider balances and bank/mobile-money statements.
        """
        from payments.models import SystemFloat

        spec = SIMULATED_FLOAT_SPECS[pool_name]
        pool = SystemFloat.objects.select_for_update().filter(name=pool_name).first()
        if pool:
            return pool

        try:
            pool = SystemFloat.objects.create(
                name=pool_name,
                currency=spec['currency'],
                balance=spec['opening_balance'],
                minimum_threshold=spec['minimum_threshold'],
                note='SIMULATED - Auto-created pool. Seed data or reconcile from live balances.',
            )
        except IntegrityError:
            pool = SystemFloat.objects.select_for_update().get(name=pool_name)
        return pool

    def _change_float_balance(self, pool_name, delta, *, transaction=None, reason='', actor=None):
        from payments.models import FloatLedgerEntry

        delta = Decimal(str(delta))
        pool = self._get_or_create_float_pool(pool_name)
        balance_before = Decimal(str(pool.balance))
        balance_after = balance_before + delta
        if balance_after < Decimal('0.00'):
            raise InsufficientFloatError(
                f"Insufficient liquidity in {pool_name}. Available {balance_before}, required {abs(delta)}."
            )

        pool.balance = balance_after
        pool.save(update_fields=['balance', 'updated_at'])

        FloatLedgerEntry.objects.create(
            system_float=pool,
            transaction=transaction,
            delta=delta,
            balance_before=balance_before,
            balance_after=balance_after,
            reason=reason or f'Balance update for {pool_name}',
            actor_label=self._actor_label(actor),
        )
        return pool

    def _sync_float_pools(self, transaction, actor=None):
        """
        Internal float accounting.

        Simulation rules:
        - Deposit: money enters the payment pool at the gross amount, and leaves the settlement pool at the net amount.
        - Withdrawal: value enters the settlement pool at the gross amount, and leaves the payout pool at the net amount.

        GO LIVE:
        - Keep this as provisional ledger logic only if it matches your real settlement model.
        - Prefer reconciling SystemFloat from actual provider balances, bank statements, and webhooks.
        - Add a proper immutable ledger table if you need audit-grade balance history.
        """
        gross_amount = transaction.amount
        net_amount = transaction.amount_after_fee
        payment_pool_name = self._pool_name_for_payment_method(transaction.payment_method)
        settlement_pool_name = self._pool_name_for_platform(transaction.platform)

        if transaction.transaction_type == 'deposit':
            self._change_float_balance(
                payment_pool_name,
                gross_amount,
                transaction=transaction,
                reason=f'{transaction.reference_code}: deposit payment received via {transaction.payment_method}',
                actor=actor,
            )
            self._change_float_balance(
                settlement_pool_name,
                -net_amount,
                transaction=transaction,
                reason=f'{transaction.reference_code}: deposit settlement sent to {transaction.platform}',
                actor=actor,
            )
            self._append_admin_note(
                transaction,
                f"Float sync: +{gross_amount} to {payment_pool_name}, -{net_amount} from {settlement_pool_name}.",
            )
        elif transaction.transaction_type == 'withdrawal':
            self._change_float_balance(
                settlement_pool_name,
                gross_amount,
                transaction=transaction,
                reason=f'{transaction.reference_code}: withdrawal settlement received from {transaction.platform}',
                actor=actor,
            )
            self._change_float_balance(
                payment_pool_name,
                -net_amount,
                transaction=transaction,
                reason=f'{transaction.reference_code}: withdrawal payout sent via {transaction.payment_method}',
                actor=actor,
            )
            self._append_admin_note(
                transaction,
                f"Float sync: +{gross_amount} to {settlement_pool_name}, -{net_amount} from {payment_pool_name}.",
            )

    def process_deposit(self, transaction, actor=None):
        """
        Deposit flow:
        - provider sends the outward asset transfer when needed
        - processor updates transaction and payment state
        """
        try:
            if transaction.platform == 'binance':
                result = self.exchange_provider.send_usdt(
                    address=transaction.destination_account,
                    amount=transaction.amount_after_fee,
                    transaction_ref=transaction.reference_code,
                )
            else:
                result = {
                    'success': True,
                    'simulated': getattr(self.exchange_provider, 'simulated', settings.SIMULATION_MODE),
                    'note': f'Manual transfer to {transaction.get_platform_display()} required',
                }

            if result['success']:
                with db_transaction.atomic():
                    transaction.status = 'completed'
                    transaction.completed_at = timezone.now()
                    self._sync_float_pools(transaction, actor=actor)
                    self._append_admin_note(
                        transaction,
                        f"Processed deposit. Transfer ref: {result.get('tx_hash', 'MANUAL')}",
                    )
                    transaction.save()

                    payment = getattr(transaction, 'payment', None)
                    self._update_payment_status(
                        payment,
                        status='confirmed',
                        confirmed=True,
                        confirmed_at=timezone.now(),
                    )
                return {'success': True, 'result': result}

            return {'success': False, 'error': result.get('error', 'Transfer failed')}

        except Exception as exc:
            transaction.status = 'rejected'
            transaction.rejection_reason = str(exc)
            transaction.completed_at = None
            self._append_admin_note(transaction, f"Processing failed: {exc}")
            transaction.save()
            self._update_payment_status(
                getattr(transaction, 'payment', None),
                status='failed',
                confirmed=False,
                confirmed_at=None,
            )
            return {'success': False, 'error': str(exc)}

    def process_withdrawal(self, transaction, payment_details=None, actor=None):
        """
        Withdrawal flow:
        - provider sends the payout
        - processor records completion and payment confirmation
        """
        try:
            if payment_details is None:
                payment = getattr(transaction, 'payment', None)
                payment_details = {
                    'phone': getattr(payment, 'payer_number', ''),
                    'bank_name': getattr(payment, 'bank_name', ''),
                    'bank_account': getattr(payment, 'bank_account', ''),
                }

            if transaction.payment_method == 'ecocash':
                result = self.payout_provider.send_payment(
                    phone_number=payment_details.get('phone'),
                    amount=transaction.amount_after_fee,
                    reference=transaction.reference_code,
                    reason=f"Withdrawal from {transaction.get_platform_display()}",
                )
            else:
                result = {
                    'success': True,
                    'simulated': getattr(self.payout_provider, 'simulated', settings.SIMULATION_MODE),
                    'note': 'Manual bank transfer required',
                }

            if result['success']:
                with db_transaction.atomic():
                    transaction.status = 'completed'
                    transaction.completed_at = timezone.now()
                    self._sync_float_pools(transaction, actor=actor)
                    self._append_admin_note(
                        transaction,
                        f"Payout sent via {transaction.get_payment_method_display()}. "
                        f"Ref: {result.get('reference', transaction.reference_code)}",
                    )
                    transaction.save()

                    payment = getattr(transaction, 'payment', None)
                    self._update_payment_status(
                        payment,
                        status='confirmed',
                        confirmed=True,
                        confirmed_at=timezone.now(),
                    )
                return {'success': True, 'result': result}

            return {'success': False, 'error': result.get('error', 'Payout failed')}

        except Exception as exc:
            transaction.status = 'rejected'
            transaction.rejection_reason = str(exc)
            transaction.completed_at = None
            self._append_admin_note(transaction, f"Processing failed: {exc}")
            transaction.save()
            self._update_payment_status(
                getattr(transaction, 'payment', None),
                status='failed',
                confirmed=False,
                confirmed_at=None,
            )
            return {'success': False, 'error': str(exc)}

    def approve_transaction(self, transaction, actor=None, note=''):
        with db_transaction.atomic():
            transaction = self._get_locked_transaction(transaction)
            if transaction.status == 'processing':
                return {'success': False, 'error': 'Processing transactions should be retried or reconciled, not approved again.'}
            if transaction.status == 'completed':
                return {'success': False, 'error': 'Completed transactions cannot be approved again.'}
            if transaction.status == 'rejected':
                return {'success': False, 'error': 'Rejected transactions must be retried instead of approved.'}

            payment = getattr(transaction, 'payment', None)
            if payment and payment.status == 'awaiting':
                self._update_payment_status(payment, status='received', confirmed=False, confirmed_at=None)

            transaction.status = 'processing'
            transaction.rejection_reason = ''
            self._append_admin_note(
                transaction,
                f"Approved by {self._actor_label(actor)}."
                + (f" Note: {note.strip()}" if note.strip() else ''),
            )
            transaction.save()
            return self.process_transaction(transaction, actor=actor)

    def reject_transaction(self, transaction, actor=None, reason=''):
        with db_transaction.atomic():
            transaction = self._get_locked_transaction(transaction)
            if transaction.status == 'completed':
                return {'success': False, 'error': 'Completed transactions cannot be rejected.'}

            rejection_reason = (reason or '').strip() or 'Rejected by admin'
            transaction.status = 'rejected'
            transaction.rejection_reason = rejection_reason
            transaction.completed_at = None
            self._append_admin_note(
                transaction,
                f"Rejected by {self._actor_label(actor)}. Reason: {rejection_reason}",
            )
            transaction.save()

            payment = getattr(transaction, 'payment', None)
            self._update_payment_status(payment, status='failed', confirmed=False, confirmed_at=None)
            return {'success': True, 'message': f'{transaction.reference_code} rejected.'}

    def retry_transaction(self, transaction, actor=None, note=''):
        with db_transaction.atomic():
            transaction = self._get_locked_transaction(transaction)
            if transaction.status == 'completed':
                return {'success': False, 'error': 'Completed transactions cannot be retried.'}
            if transaction.status == 'pending':
                return {'success': False, 'error': 'Pending transactions should be approved instead of retried.'}

            payment = getattr(transaction, 'payment', None)
            transaction.status = 'processing'
            transaction.rejection_reason = ''
            transaction.completed_at = None
            self._append_admin_note(
                transaction,
                f"Retry requested by {self._actor_label(actor)}."
                + (f" Note: {note.strip()}" if note.strip() else ''),
            )
            transaction.save()

            if payment:
                retry_payment_status = 'received' if transaction.transaction_type == 'deposit' else 'awaiting'
                self._update_payment_status(
                    payment,
                    status=retry_payment_status,
                    confirmed=False,
                    confirmed_at=None,
                )

            return self.process_transaction(transaction, actor=actor)

    def reconcile_transaction(self, transaction, actor=None, note=''):
        with db_transaction.atomic():
            transaction = self._get_locked_transaction(transaction)
            payment = getattr(transaction, 'payment', None)
            changes = []

            if payment:
                if transaction.status == 'completed':
                    self._update_payment_status(
                        payment,
                        status='confirmed',
                        confirmed=True,
                        confirmed_at=payment.confirmed_at or timezone.now(),
                    )
                    changes.append('payment marked confirmed')
                elif transaction.status == 'rejected':
                    self._update_payment_status(payment, status='failed', confirmed=False, confirmed_at=None)
                    changes.append('payment marked failed')
                elif transaction.status == 'processing':
                    self._update_payment_status(payment, status='received', confirmed=False, confirmed_at=None)
                    changes.append('payment marked received')
                elif transaction.status == 'pending':
                    if payment.status == 'confirmed':
                        transaction.status = 'processing'
                        changes.append('transaction moved to processing because payment was already confirmed')
                    elif payment.status == 'failed':
                        transaction.status = 'rejected'
                        transaction.rejection_reason = transaction.rejection_reason or 'Reconciled from failed payment'
                        changes.append('transaction moved to rejected because payment had failed')
                    else:
                        self._update_payment_status(payment, status='awaiting', confirmed=False, confirmed_at=None)
                        changes.append('payment reset to awaiting')
            else:
                changes.append('no payment record found')

            self._append_admin_note(
                transaction,
                f"Reconciled by {self._actor_label(actor)}."
                + (f" Note: {note.strip()}" if note.strip() else '')
                + (f" Changes: {', '.join(changes)}." if changes else ''),
            )
            transaction.save()
            return {
                'success': True,
                'message': f"{transaction.reference_code} reconciled.",
                'changes': changes,
            }

    def process_transaction(self, transaction, actor=None):
        with db_transaction.atomic():
            transaction = self._get_locked_transaction(transaction)
            if transaction.status == 'completed':
                return {'success': False, 'error': 'Completed transactions cannot be processed again.'}
            if transaction.status == 'rejected':
                return {'success': False, 'error': 'Rejected transactions must be retried before processing.'}
            if transaction.transaction_type == 'deposit':
                return self.process_deposit(transaction, actor=actor)
            if transaction.transaction_type == 'withdrawal':
                return self.process_withdrawal(transaction, actor=actor)
            return {'success': False, 'error': f'Unsupported transaction type: {transaction.transaction_type}'}

    def get_current_rates(self):
        provider_error = ''
        try:
            rate = self.exchange_provider.get_current_rate()
        except ProviderConfigurationError as exc:
            rate = 1.0
            provider_error = str(exc)

        try:
            from payments.models import FeeSettings

            fee_settings = FeeSettings.get_solo()
            deposit_fee = Decimal(str(fee_settings.deposit_fee_percent))
            withdrawal_fee = Decimal(str(fee_settings.withdrawal_fee_percent))
        except Exception:
            deposit_fee = Decimal(str(getattr(settings, 'DEFAULT_DEPOSIT_FEE_PERCENT', 3.0)))
            withdrawal_fee = Decimal(str(getattr(settings, 'DEFAULT_WITHDRAWAL_FEE_PERCENT', 3.0)))

        rate_decimal = Decimal(str(rate))
        deposit_effective_rate = (rate_decimal * (Decimal('1.00') - deposit_fee / Decimal('100'))).quantize(Decimal('0.0001'))
        withdrawal_effective_rate = (Decimal('1.00') - withdrawal_fee / Decimal('100')).quantize(Decimal('0.0001'))

        return {
            'usdt_rate': rate,
            'fee_percent': deposit_fee,
            'deposit_fee_percent': deposit_fee,
            'withdrawal_fee_percent': withdrawal_fee,
            'effective_rate': deposit_effective_rate,
            'deposit_effective_rate': deposit_effective_rate,
            'withdrawal_effective_rate': withdrawal_effective_rate,
            'simulated': getattr(self.exchange_provider, 'simulated', settings.SIMULATION_MODE),
            'provider_error': provider_error,
        }
