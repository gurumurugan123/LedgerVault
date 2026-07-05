from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ledger.models import AuditAction, AuditLog
from apps.ledger.serializers import AdminUserRoleSerializer
from apps.ledger.audit_service import log_audit
from apps.users.models import User
from apps.users.permissions import IsAdmin


class AdministrationUserListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        users = User.objects.order_by("id")
        return Response(
            [
                {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                    "is_active": user.is_active,
                    "created_at": user.created_at,
                }
                for user in users
            ]
        )


class AdministrationUserRoleView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        serializer = AdminUserRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_role = serializer.validated_data["role"]
        if user.id == request.user.id and new_role != request.user.role:
            return Response(
                {"detail": "You cannot change your own role."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_role = user.role
        if old_role == new_role:
            return Response(
                {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                }
            )

        user.role = new_role
        user.save(update_fields=["role"])

        log_audit(
            actor=request.user,
            action=AuditAction.USER_ROLE_CHANGED,
            target_type="user",
            target_id=user.id,
            metadata={
                "email": user.email,
                "old_role": old_role,
                "new_role": new_role,
            },
        )

        return Response(
            {
                "id": user.id,
                "email": user.email,
                "role": user.role,
            }
        )


class AdministrationAuditLogListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        queryset = AuditLog.objects.select_related("actor").order_by("-created_at")

        action_filter = request.query_params.get("action", "").strip()
        if action_filter:
            if action_filter not in AuditAction.values:
                return Response(
                    {
                        "detail": f"Invalid action. Choose from: {', '.join(AuditAction.values)}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(action=action_filter)

        actor_email = request.query_params.get("actor_email", "").strip()
        if actor_email:
            queryset = queryset.filter(actor__email__iexact=actor_email)

        results = [
            {
                "id": entry.id,
                "action": entry.action,
                "target_type": entry.target_type,
                "target_id": entry.target_id,
                "metadata": entry.metadata,
                "actor_email": entry.actor.email if entry.actor else None,
                "created_at": entry.created_at,
            }
            for entry in queryset[:100]
        ]
        return Response(results)
