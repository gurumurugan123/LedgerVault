from django.urls import path

from apps.ledger.administration_views import (
    AdministrationAuditLogListView,
    AdministrationUserListView,
    AdministrationUserRoleView,
)

urlpatterns = [
    path("users/", AdministrationUserListView.as_view(), name="administration-user-list"),
    path("users/<int:pk>/role/", AdministrationUserRoleView.as_view(), name="administration-user-role"),
    path("audit-logs/", AdministrationAuditLogListView.as_view(), name="administration-audit-log-list"),
]
