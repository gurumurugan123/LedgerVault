import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0001_initial"),
        ("ledger", "0002_idempotencykey"),
    ]

    operations = [
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.CharField(db_index=True, max_length=64, unique=True)),
                ("direction", models.CharField(choices=[("TOPUP", "Top-up"), ("WITHDRAWAL", "Withdrawal")], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=18)),
                (
                    "status",
                    models.CharField(
                        choices=[("PENDING", "Pending"), ("COMPLETED", "Completed"), ("FAILED", "Failed")],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("webhook_event_id", models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "transaction",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payment",
                        to="ledger.transaction",
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payments",
                        to="wallets.wallet",
                    ),
                ),
            ],
            options={
                "db_table": "payments",
                "ordering": ["-created_at"],
            },
        ),
    ]
