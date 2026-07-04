from rest_framework import serializers

from apps.wallets.models import Wallet


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ("id", "name", "currency", "created_at")
        read_only_fields = ("id", "created_at")


class WalletBalanceSerializer(serializers.Serializer):
    wallet_id = serializers.IntegerField()
    currency = serializers.CharField()
    balance = serializers.DecimalField(max_digits=18, decimal_places=2)


class LedgerEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    status = serializers.CharField()
    transaction_id = serializers.IntegerField(source="transaction.id")
    transaction_type = serializers.CharField(source="transaction.type")
    created_at = serializers.DateTimeField()
