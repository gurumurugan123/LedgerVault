import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
        ("ledger", "0003_payment"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("REVERSAL_CREATED", "Reversal created"),
                            ("PAYMENT_WEBHOOK", "Payment webhook processed"),
                            ("USER_ROLE_CHANGED", "User role changed"),
                        ],
                        max_length=40,
                    ),
                ),
                ("target_type", models.CharField(max_length=40)),
                ("target_id", models.CharField(max_length=64)),
                ("metadata", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="users.user",
                    ),
                ),
            ],
            options={
                "db_table": "audit_logs",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["action", "created_at"], name="audit_logs_action_created_idx"),
                    models.Index(fields=["target_type", "target_id"], name="audit_logs_target_idx"),
                ],
            },
        ),
    ]
