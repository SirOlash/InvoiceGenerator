from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Invoice
from .serializers import InvoiceSerializer


class IsOwnerOr404:
    """
    Lightweight object-level check implemented inside get_object().
    We don't create a separate permission class because we want to *hide*
    non-owned objects (404) rather than return 403.
    """
    # dummy container for intent only


class InvoiceViewSet(viewsets.ModelViewSet):
    """
    Handles:
      - list:  GET /api/invoices/        -> invoices for request.user
      - retrieve: GET /api/invoices/{pk}/ -> invoice detail (must belong to user)
      - create: POST /api/invoices/       -> create invoice + items (handled by serializer)
      - update/partial_update/destroy: allowed only for owner's invoices
    Important:
      - creation is performed with serializer.create(), which already uses the request user
        (your InvoiceSerializer.create() expects `self.context['request'].user`).
    """
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        return Invoice.objects.filter(created_by=self.request.user).order_by("-created_at")

    def get_object(self):
        queryset = self.get_queryset()
        obj = get_object_or_404(queryset, pk=self.kwargs.get(self.lookup_field))
        return obj

    def perform_create(self, serializer):
        serializer.save()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        invoice = Invoice.objects.get(pk=serializer.instance.pk)
        out_serializer = self.get_serializer(invoice)
        headers = self.get_success_headers(out_serializer.data)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
