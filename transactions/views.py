from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.db import transaction as db_transaction
from django.views.decorators.http import require_POST
from .models import Transaction
from .forms import DepositForm, WithdrawalForm
from .services import TransactionProcessor
from payments.models import FeeSettings, Payment
from forex_gateway.rate_limits import rate_limit, user_key


processor = TransactionProcessor()


@login_required
@rate_limit('transaction_submit_user', key_func=user_key, methods=('POST',))
def deposit_view(request):
    rates = processor.get_current_rates()
    fee_settings = FeeSettings.get_solo()
    if request.method == 'POST':
        form = DepositForm(request.POST)
        if form.is_valid():
            with db_transaction.atomic():
                transaction = form.save(commit=False)
                transaction.user = request.user
                transaction.transaction_type = 'deposit'
                transaction.save()

                Payment.objects.create(
                    transaction=transaction,
                    amount=transaction.amount,
                    **form.get_payment_data(),
                )

            messages.success(request, f'Deposit request submitted! Reference: {transaction.reference_code}')
            return redirect('transaction_detail', pk=transaction.pk)
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = DepositForm()

    return render(request, 'transactions/deposit.html', {
        'form': form,
        'rates': rates,
        'ecocash_number': settings.ECOCASH_NUMBER,
        'bank_name': settings.BANK_NAME,
        'bank_account': settings.BANK_ACCOUNT,
        'deposit_fee_percent': fee_settings.deposit_fee_percent,
        'simulation_mode': settings.SIMULATION_MODE,
    })


@login_required
@rate_limit('transaction_submit_user', key_func=user_key, methods=('POST',))
def withdrawal_view(request):
    rates = processor.get_current_rates()
    fee_settings = FeeSettings.get_solo()
    if request.method == 'POST':
        form = WithdrawalForm(request.POST)
        if form.is_valid():
            with db_transaction.atomic():
                transaction = form.save(commit=False)
                transaction.user = request.user
                transaction.transaction_type = 'withdrawal'
                transaction.save()

                Payment.objects.create(
                    transaction=transaction,
                    amount=transaction.amount,
                    **form.get_payment_data(),
                )

            messages.success(request, f'Withdrawal request submitted! Reference: {transaction.reference_code}')
            return redirect('transaction_detail', pk=transaction.pk)
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = WithdrawalForm()

    return render(request, 'transactions/withdrawal.html', {
        'form': form,
        'rates': rates,
        'withdrawal_fee_percent': fee_settings.withdrawal_fee_percent,
        'simulation_mode': settings.SIMULATION_MODE,
    })


@login_required
def transaction_list_view(request):
    transactions = Transaction.objects.filter(user=request.user)
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    if status_filter:
        transactions = transactions.filter(status=status_filter)
    if type_filter:
        transactions = transactions.filter(transaction_type=type_filter)
    return render(request, 'transactions/list.html', {
        'transactions': transactions,
        'status_filter': status_filter,
        'type_filter': type_filter,
    })


@login_required
def transaction_detail_view(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, user=request.user)
    return render(request, 'transactions/detail.html', {
        'transaction': transaction,
        'ecocash_number': settings.ECOCASH_NUMBER,
        'simulation_mode': settings.SIMULATION_MODE,
    })


@login_required
@require_POST
@rate_limit('transaction_action_user', key_func=user_key, methods=('POST',))
def simulate_payment_view(request, pk):
    """SIMULATION ONLY: Instantly marks payment as received and processes it"""
    if not settings.SIMULATION_MODE:
        messages.error(request, 'Simulation mode is disabled.')
        return redirect('transaction_detail', pk=pk)

    transaction = get_object_or_404(Transaction, pk=pk, user=request.user)
    with db_transaction.atomic():
        transaction = get_object_or_404(
            Transaction.objects.select_for_update().select_related('payment'),
            pk=pk,
            user=request.user,
        )
        if transaction.status == 'pending':
            transaction.status = 'processing'
            transaction.save(update_fields=['status', 'updated_at'])
            should_process = True
        else:
            should_process = False

    if should_process:
        result = processor.process_transaction(transaction, actor=request.user)
        if result['success']:
            if transaction.transaction_type == 'deposit':
                messages.success(request, '🟢 SIMULATED: Payment confirmed and funds sent automatically!')
            else:
                messages.success(request, '🟢 SIMULATED: Withdrawal payout sent successfully!')
        else:
            messages.error(request, f'Simulation error: {result.get("error")}')
    else:
        messages.info(request, f'Transaction is already {transaction.status}.')
    return redirect('transaction_detail', pk=pk)


@login_required
@require_POST
@rate_limit('transaction_action_user', key_func=user_key, methods=('POST',))
def cancel_transaction_view(request, pk):
    with db_transaction.atomic():
        transaction = get_object_or_404(
            Transaction.objects.select_for_update(),
            pk=pk,
            user=request.user,
        )
        if transaction.status == 'pending':
            transaction.status = 'rejected'
            transaction.rejection_reason = 'Cancelled by user'
            transaction.save(update_fields=['status', 'rejection_reason', 'updated_at'])
            cancelled = True
        else:
            cancelled = False

    if cancelled:
        messages.success(request, 'Transaction cancelled.')
    else:
        messages.error(request, 'Only pending transactions can be cancelled.')
    return redirect('transaction_list')


def rates_view(request):
    rates = processor.get_current_rates()
    return render(request, 'transactions/rates.html', {'rates': rates})
