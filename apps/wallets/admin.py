from django.contrib import admin

from apps.wallets.models import Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "currency", "created_at")
    list_filter = ("currency",)
    search_fields = ("name", "user__email")
