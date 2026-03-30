from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from payments.forms import FeeSettingsForm
from payments.models import FeeSettings, FeeSettingsAuditLog, FloatLedgerEntry, Payment, SystemFloat
from transactions.models import Transaction
from transactions.services import TransactionProcessor
from forex_gateway.rate_limits import rate_limit, user_key


processor = TransactionProcessor()


def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    try:
        fee_settings = FeeSettings.get_solo()
        deposit_fee_percent = fee_settings.deposit_fee_percent
        withdrawal_fee_percent = fee_settings.withdrawal_fee_percent
    except Exception:
        deposit_fee_percent = Decimal('3.00')
        withdrawal_fee_percent = Decimal('3.00')
    sample_amount = Decimal('100.00')
    sample_fee = (sample_amount * deposit_fee_percent / Decimal('100')).quantize(Decimal('0.01'))
    sample_credit = sample_amount - sample_fee
    return render(request, 'home.html', {
        'deposit_fee_percent': deposit_fee_percent,
        'withdrawal_fee_percent': withdrawal_fee_percent,
        'sample_deposit_fee': sample_fee,
        'sample_deposit_credit': sample_credit,
    })


@login_required
def dashboard_view(request):
    user_transactions = Transaction.objects.filter(user=request.user)
    stats = {
        'total': user_transactions.count(),
        'pending': user_transactions.filter(status='pending').count(),
        'processing': user_transactions.filter(status='processing').count(),
        'completed': user_transactions.filter(status='completed').count(),
        'rejected': user_transactions.filter(status='rejected').count(),
        'total_deposited': sum(
            t.amount for t in user_transactions.filter(transaction_type='deposit', status='completed')
        ),
        'total_withdrawn': sum(
            t.amount for t in user_transactions.filter(transaction_type='withdrawal', status='completed')
        ),
    }
    recent = user_transactions[:5]
    rates = processor.get_current_rates()
    return render(request, 'dashboard/dashboard.html', {
        'stats': stats,
        'recent_transactions': recent,
        'rates': rates,
    })


def _staff_only(request):
    if request.user.is_staff:
        return None
    return HttpResponseForbidden("Admin access required.")


@login_required
def admin_dashboard_view(request):
    forbidden = _staff_only(request)
    if forbidden:
        return forbidden

    all_transactions = Transaction.objects.all().select_related('user', 'payment')
    status_filter = request.GET.get('status', '').strip()
    type_filter = request.GET.get('type', '').strip()
    search_query = request.GET.get('q', '').strip()

    filtered_transactions = all_transactions
    if status_filter:
        filtered_transactions = filtered_transactions.filter(status=status_filter)
    if type_filter:
        filtered_transactions = filtered_transactions.filter(transaction_type=type_filter)
    if search_query:
        filtered_transactions = filtered_transactions.filter(
            Q(reference_code__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(user__first_name__icontains=search_query)
            | Q(user__last_name__icontains=search_query)
            | Q(user__email__icontains=search_query)
        )

    stats = {
        'total_users': get_user_model().objects.count(),
        'pending': all_transactions.filter(status='pending').count(),
        'processing': all_transactions.filter(status='processing').count(),
        'completed': all_transactions.filter(status='completed').count(),
        'rejected': all_transactions.filter(status='rejected').count(),
        'total_volume': sum(t.amount for t in all_transactions.filter(status='completed')),
        'total_fees': sum(t.fee for t in all_transactions.filter(status='completed')),
    }
    payment_stats = {
        'awaiting': Payment.objects.filter(status='awaiting').count(),
        'received': Payment.objects.filter(status='received').count(),
        'confirmed': Payment.objects.filter(status='confirmed').count(),
        'failed': Payment.objects.filter(status='failed').count(),
    }
    fee_settings = FeeSettings.get_solo()
    floats = SystemFloat.objects.all()
    return render(request, 'dashboard/admin.html', {
        'stats': stats,
        'payment_stats': payment_stats,
        'transactions': filtered_transactions[:30],
        'floats': floats,
        'fee_settings': fee_settings,
        'fee_settings_form': FeeSettingsForm(instance=fee_settings),
        'recent_float_ledger': FloatLedgerEntry.objects.select_related('system_float', 'transaction')[:10],
        'recent_fee_changes': FeeSettingsAuditLog.objects.select_related('changed_by', 'fee_settings')[:10],
        'status_filter': status_filter,
        'type_filter': type_filter,
        'search_query': search_query,
    })


@login_required
@require_POST
@rate_limit('admin_action_user', key_func=user_key, methods=('POST',))
def admin_transaction_action_view(request, pk):
    forbidden = _staff_only(request)
    if forbidden:
        return forbidden

    transaction = get_object_or_404(Transaction.objects.select_related('payment', 'user'), pk=pk)
    action = request.POST.get('action', '').strip()
    note = request.POST.get('note', '').strip()
    next_url = request.POST.get('next') or 'admin_panel'

    if action == 'approve':
        result = processor.approve_transaction(transaction, actor=request.user, note=note)
    elif action == 'reject':
        result = processor.reject_transaction(transaction, actor=request.user, reason=note)
    elif action == 'retry':
        result = processor.retry_transaction(transaction, actor=request.user, note=note)
    elif action == 'reconcile':
        result = processor.reconcile_transaction(transaction, actor=request.user, note=note)
    else:
        messages.error(request, 'Unknown admin action.')
        return redirect(next_url)

    if result.get('success'):
        messages.success(
            request,
            result.get('message') or f"{transaction.reference_code}: {action.title()} completed successfully."
        )
    else:
        messages.error(
            request,
            result.get('error') or f"{transaction.reference_code}: {action.title()} failed."
        )
    return redirect(next_url)


@login_required
@require_POST
@rate_limit('admin_action_user', key_func=user_key, methods=('POST',))
def admin_fee_settings_update_view(request):
    forbidden = _staff_only(request)
    if forbidden:
        return forbidden

    fee_settings = FeeSettings.get_solo()
    previous_deposit_fee_percent = fee_settings.deposit_fee_percent
    previous_withdrawal_fee_percent = fee_settings.withdrawal_fee_percent
    form = FeeSettingsForm(request.POST, instance=fee_settings)
    if form.is_valid():
        fee_settings = form.save()
        fee_settings.record_change(
            previous_deposit_fee_percent=previous_deposit_fee_percent,
            previous_withdrawal_fee_percent=previous_withdrawal_fee_percent,
            actor=request.user,
            source='admin_panel',
        )
        messages.success(request, 'Fee settings updated. New transactions will use the new fee percentages.')
    else:
        messages.error(request, 'Could not update fee settings. Please correct the errors and try again.')
    return redirect('admin_panel')
