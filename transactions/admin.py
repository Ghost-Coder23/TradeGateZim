from django.contrib import admin
from .models import ProviderWebhookEvent, Transaction
from .services import TransactionProcessor

processor = TransactionProcessor()

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'reference_code',
        'user',
        'transaction_type',
        'platform',
        'amount',
        'destination_account_type',
        'payment_method',
        'status',
        'provider_status',
        'provider_reference',
        'created_at',
    ]
    list_filter = ['status', 'transaction_type', 'platform', 'payment_method', 'destination_account_type']
    search_fields = ['reference_code', 'user__username', 'user__email', 'destination_account']
    readonly_fields = [
        'reference_code',
        'fee_percent_applied',
        'fee',
        'amount_after_fee',
        'provider_status',
        'provider_reference',
        'provider_error_code',
        'provider_error_message',
        'provider_payload',
        'provider_last_synced_at',
        'created_at',
        'updated_at',
        'completed_at',
    ]
    ordering = ['-created_at']
    actions = ['approve_and_process', 'mark_processing', 'mark_rejected', 'retry_selected', 'reconcile_selected']

    def approve_and_process(self, request, queryset):
        for tx in queryset.filter(status__in=['pending', 'processing']):
            result = processor.approve_transaction(tx, actor=request.user)
            if result['success']:
                self.message_user(
                    request,
                    f"{tx.reference_code}: {tx.get_transaction_type_display()} processed successfully."
                )
            else:
                self.message_user(request, f"{tx.reference_code}: Failed — {result.get('error')}", level='error')
    approve_and_process.short_description = "Approve & Process Selected"

    def mark_processing(self, request, queryset):
        queryset.filter(status='pending').update(status='processing')
        self.message_user(request, f"{queryset.count()} transaction(s) marked as processing.")
    mark_processing.short_description = "Mark as Processing"

    def mark_rejected(self, request, queryset):
        processed = 0
        for tx in queryset.exclude(status='completed'):
            result = processor.reject_transaction(tx, actor=request.user)
            if result['success']:
                processed += 1
        self.message_user(request, f"{processed} transaction(s) rejected.")
    mark_rejected.short_description = "Reject Selected"

    def retry_selected(self, request, queryset):
        processed = 0
        for tx in queryset.exclude(status='completed'):
            result = processor.retry_transaction(tx, actor=request.user)
            if result['success']:
                processed += 1
            else:
                self.message_user(request, f"{tx.reference_code}: Retry failed — {result.get('error')}", level='error')
        self.message_user(request, f"{processed} transaction(s) retried.")
    retry_selected.short_description = "Retry Selected"

    def reconcile_selected(self, request, queryset):
        for tx in queryset:
            processor.reconcile_transaction(tx, actor=request.user)
        self.message_user(request, f"{queryset.count()} transaction(s) reconciled.")
    reconcile_selected.short_description = "Reconcile Selected"


@admin.register(ProviderWebhookEvent)
class ProviderWebhookEventAdmin(admin.ModelAdmin):
    list_display = [
        'provider',
        'event_type',
        'external_event_id',
        'reference_code',
        'transaction',
        'signature_status',
        'processing_status',
        'received_at',
    ]
    list_filter = ['provider', 'signature_status', 'processing_status', 'received_at']
    search_fields = ['external_event_id', 'reference_code', 'transaction__reference_code', 'processing_notes']
    readonly_fields = [field.name for field in ProviderWebhookEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
