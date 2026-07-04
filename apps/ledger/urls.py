from django.urls import path

from apps.ledger.views import TransferView

urlpatterns = [
    path("", TransferView.as_view(), name="transfer-create"),
]
