from django.urls import path

from apps.ledger.reversal_views import ReversalView

urlpatterns = [
    path("", ReversalView.as_view(), name="reversal-create"),
]
