from django.contrib import admin

from apps.ledger.models import IdempotencyKey, LedgerEntry, Transaction


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
