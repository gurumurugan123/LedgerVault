from django.contrib import admin

from apps.ledger.models import AuditLog, IdempotencyKey, LedgerEntry, Payment, Transaction


class LedgerEntryInline(admin.TabularInline):
    model = LedgerEntry
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "reference_transaction", "created_at")
    list_filter = ("type",)
    inlines = [LedgerEntryInline]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "wallet", "type", "amount", "status", "transaction", "created_at")
    list_filter = ("type", "status")
    search_fields = ("wallet__name", "wallet__user__email")


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ("key", "status_code", "created_at")
    search_fields = ("key",)
    readonly_fields = ("response_body", "created_at")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("external_id", "wallet", "direction", "amount", "status", "created_at")
    list_filter = ("direction", "status")
    search_fields = ("external_id", "wallet__name", "wallet__user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "action", "target_type", "target_id", "actor", "created_at")
    list_filter = ("action", "target_type")
    search_fields = ("target_id", "actor__email")
    readonly_fields = ("metadata", "created_at")
