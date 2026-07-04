from decimal import Decimal

from rest_framework import serializers


class TransferSerializer(serializers.Serializer):
    from_wallet_id = serializers.IntegerField()
    to_wallet_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
