from django.conf import settings
from django.db import models


class Wallet(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallets",
    )
    name = models.CharField(max_length=100)
    currency = models.CharField(max_length=3, default="INR")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wallets"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_wallet_name_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.currency})"
