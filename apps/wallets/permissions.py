from rest_framework.permissions import BasePermission


class IsWalletOwner(BasePermission):
    message = "You do not have access to this wallet."

    def has_object_permission(self, request, view, obj):
        return obj.user_id == request.user.id
