from rest_framework.permissions import BasePermission

from apps.users.models import UserRole


class IsAdmin(BasePermission):
    message = "Admin role required."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.ADMIN
        )


class IsSupport(BasePermission):
    message = "Support or admin role required."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in (UserRole.SUPPORT, UserRole.ADMIN)
        )


class IsCustomer(BasePermission):
    message = "Customer role required."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.CUSTOMER
        )
