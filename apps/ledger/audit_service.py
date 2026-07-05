from apps.ledger.models import AuditLog


def log_audit(*, actor, action: str, target_type: str, target_id, metadata=None) -> AuditLog:
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        metadata=metadata or {},
    )
