import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from billing.models import Invoice, InvoiceItem, Client

User = get_user_model()


@pytest.mark.django_db
class TestInvoiceApiCreate:
    def setup_method(self):
        self.client = APIClient()

    def test_create_invoice_without_client_info(self):
        """If no client email or phone is provided, no Client is created and invoice/items are saved."""
        user = User.objects.create_user(email="testuser@example.com", password="pass1234")
        self.client.force_authenticate(user)

        payload = {
            "client_name": "Anonymous Buyer",
            "client_email": "",
            "client_phone": "",
            "client_address": "",
            "seller_name": "My Store",
            "seller_email": "seller@test.com",
            "seller_phone": "09011112222",
            "currency": "NGN",
            "discount_amount": "0.00",
            "items": [
                {"description": "Item A", "quantity": "2", "unit_price": "1000", "discount": "0"},
                {"description": "Item B", "quantity": "1", "unit_price": "500", "discount": "0"},
            ],
        }

        url = reverse("billing:invoice-list")
        resp = self.client.post(url, payload, format="json")
        assert resp.status_code == 201, resp.data

        assert Invoice.objects.filter(created_by=user).count() == 1
        assert InvoiceItem.objects.filter(invoice__created_by=user).count() == 2
        assert Client.objects.filter(created_by=user).count() == 0

        invoice = Invoice.objects.get(created_by=user)
        # subtotal = 2*1000 + 1*500 = 2500 -> total stored as whole number = 2500
        assert invoice.total == Decimal("2500")

    def test_create_invoice_with_new_client(self):
        """If client email or phone provided, a new Client should be created and linked."""
        user = User.objects.create_user(email="seller@example.com", password="pass1234")
        self.client.force_authenticate(user)

        payload = {
            "client_name": "Emmanuel",
            "client_email": "emmanuel@test.com",
            "client_phone": "08100000000",
            "client_address": "Lagos",
            "seller_name": "My Shop",
            "currency": "NGN",
            "items": [
                {"description": "Laptop", "quantity": "1", "unit_price": "250000", "discount": "0"},
            ],
        }

        url = reverse("billing:invoice-list")
        resp = self.client.post(url, payload, format="json")
        assert resp.status_code == 201, resp.data

        invoice = Invoice.objects.get(created_by=user)
        client = Client.objects.get(created_by=user, email__iexact="emmanuel@test.com")
        assert invoice.client == client
        assert invoice.client_name == "Emmanuel"

    def test_reuse_existing_client_and_update(self):
        """If a client already exists (same email or phone), link to it and update missing fields."""
        user = User.objects.create_user(email="userx@example.com", password="pass1234")
        existing_client = Client.objects.create(
            created_by=user,
            name="Existing Client",
            email="existing@test.com",
            phone="09099999999",
        )

        self.client.force_authenticate(user)

        payload = {
            "client_name": "Existing Client Updated",
            "client_email": "existing@test.com",
            "client_phone": "09099999999",
            "client_address": "New Address",
            "seller_name": "My Biz",
            "currency": "NGN",
            "items": [
                {"description": "Shoes", "quantity": "1", "unit_price": "15000", "discount": "0"},
            ],
        }

        url = reverse("billing:invoice-list")
        resp = self.client.post(url, payload, format="json")
        assert resp.status_code == 201, resp.data

        existing_client.refresh_from_db()
        invoice = Invoice.objects.get(created_by=user)
        assert Client.objects.filter(created_by=user).count() == 1
        assert invoice.client == existing_client
        assert existing_client.address == "New Address"
