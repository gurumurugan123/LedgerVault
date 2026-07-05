from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health_check(_request):
    return JsonResponse({"status": "ok", "project": "LedgerVault"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health"),
    path("auth/", include("apps.users.urls")),
    path("wallets/", include("apps.wallets.urls")),
    path("transfers/", include("apps.ledger.urls")),
    path("", include("apps.ledger.payment_urls")),
]
