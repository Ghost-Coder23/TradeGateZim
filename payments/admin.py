from django.contrib import admin

from .models import ExchangeRate, FeeSettings, FeeSettingsAuditLog, FloatLedgerEntry, Payment, SystemFloat


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'payer_number', 'amount', 'status', 'confirmed', 'created_at']
    list_filter = ['status', 'confirmed']
    search_fields = ['transaction__reference_code', 'payer_number']


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ['currency_pair', 'rate', 'spread_percent', 'effective_rate', 'is_simulated', 'fetched_at']


@admin.register(FeeSettings)
class FeeSettingsAdmin(admin.ModelAdmin):
    list_display = ['deposit_fee_percent', 'withdrawal_fee_percent', 'updated_at']
    readonly_fields = ['updated_at']

    def has_add_permission(self, request):
        return not FeeSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change and obj.pk:
            previous = FeeSettings.objects.get(pk=obj.pk)
            previous_deposit_fee_percent = previous.deposit_fee_percent
            previous_withdrawal_fee_percent = previous.withdrawal_fee_percent
        else:
            previous_deposit_fee_percent = obj.deposit_fee_percent
            previous_withdrawal_fee_percent = obj.withdrawal_fee_percent

        super().save_model(request, obj, form, change)
        obj.record_change(
            previous_deposit_fee_percent=previous_deposit_fee_percent,
            previous_withdrawal_fee_percent=previous_withdrawal_fee_percent,
            actor=request.user,
            source='django_admin',
        )


@admin.register(SystemFloat)
class SystemFloatAdmin(admin.ModelAdmin):
    list_display = ['name', 'currency', 'balance', 'minimum_threshold', 'is_simulated', 'updated_at']


@admin.register(FloatLedgerEntry)
class FloatLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ['system_float', 'delta', 'balance_before', 'balance_after', 'reason', 'actor_label', 'created_at']
    list_filter = ['system_float', 'created_at']
    search_fields = ['reason', 'actor_label', 'transaction__reference_code']
    readonly_fields = [field.name for field in FloatLedgerEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(FeeSettingsAuditLog)
class FeeSettingsAuditLogAdmin(admin.ModelAdmin):
    list_display = [
        'fee_settings',
        'previous_deposit_fee_percent',
        'new_deposit_fee_percent',
        'previous_withdrawal_fee_percent',
        'new_withdrawal_fee_percent',
        'changed_by_label',
        'source',
        'created_at',
    ]
    list_filter = ['source', 'created_at']
    search_fields = ['changed_by_label', 'note']
    readonly_fields = [field.name for field in FeeSettingsAuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
