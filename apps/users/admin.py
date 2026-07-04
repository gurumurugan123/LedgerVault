from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.users.models import RefreshToken, User, UserRole


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "role", "is_active", "is_staff", "created_at")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Role & status", {"fields": ("role", "is_active", "is_staff", "is_superuser")}),
        ("Permissions", {"fields": ("groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "created_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "role"),
            },
        ),
    )
    readonly_fields = ("created_at", "last_login")

    def save_model(self, request, obj, form, change):
        if obj.role == UserRole.ADMIN:
            obj.is_staff = True
        super().save_model(request, obj, form, change)


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "revoked", "expires_at", "created_at")
    list_filter = ("revoked",)
    search_fields = ("user__email",)
    readonly_fields = ("token_hash", "created_at")
