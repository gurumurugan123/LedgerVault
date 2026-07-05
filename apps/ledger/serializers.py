from decimal import Decimal

from rest_framework import serializers

from apps.users.models import UserRole


class TransferSerializer(serializers.Serializer):
    from_wallet_id = serializers.IntegerField()
    to_wallet_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))


class WalletPaymentSerializer(serializers.Serializer):
    wallet_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))


class PaymentWebhookSerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=255)
    payment_id = serializers.CharField(max_length=64)
    status = serializers.CharField(max_length=20)


class ReversalSerializer(serializers.Serializer):
    transaction_id = serializers.IntegerField(min_value=1)


class AdminUserRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=UserRole.choices)

