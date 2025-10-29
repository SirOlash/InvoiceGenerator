from rest_framework import serializers
from decimal import Decimal
from django.db import transaction
from .models import Invoice, InvoiceItem, Client
import re

PHONE_DIGITS_RE = re.compile(r'\D+')


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = [
            "id",
            "description",
            "quantity",
            "unit_price",
            "discount",
            "amount",
            "notes",
            "order",
        ]
        read_only_fields = ["id", "amount"]

    def validate(self, data):
        qty = data.get("quantity", Decimal("0"))
        rate = data.get("unit_price", Decimal("0"))
        discount = data.get("discount", Decimal("0"))
        if qty < 0 or rate < 0 or discount < 0:
            raise serializers.ValidationError("Quantity, rate, and discount must be non-negative.")
        return data


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ["id", "name", "email", "phone", "address"]
        read_only_fields = ["id"]


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, write_only=True)
    items_detail = InvoiceItemSerializer(source="items", many=True, read_only=True)
    # expose client as nested read-only for GETs (invoice shows client details)
    client = ClientSerializer(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "public_uuid",
            "invoice_number",
            "issue_date",
            "due_date",
            "status",
            "currency",
            "seller_name",
            "seller_email",
            "seller_phone",
            "seller_address",
            "seller_logo",
            "client",              # nested read-only representation
            "client_name",         # snapshot - required in invoice
            "client_email",
            "client_phone",
            "client_address",
            "subtotal",
            "discount_amount",
            "total",
            "notes",
            "image",
            "payment_url",
            "pdf_file",
            "created_at",
            "updated_at",
            "items",
            "items_detail",
        ]

        read_only_fields = [
            "id",
            "public_uuid",
            "invoice_number",
            "subtotal",
            "discount_amount",
            "total",
            "created_at",
            "updated_at",
            "items_detail",
            "client",  # client FK is set server-side during create if applicable
        ]

    def validate(self, data):
        """
        Ensure there's at least a client_name (invoice always needs a name to display).
        Normalize phone to digits-only when provided.
        """
        client_name = data.get("client_name") or data.get("client", {}).get("name")
        if not client_name:
            raise serializers.ValidationError({"client_name": "Client name is required."})

        phone = data.get("client_phone")
        if phone:
            # normalize digits only (keeps +/spaces/dashes out)
            digits = PHONE_DIGITS_RE.sub("", str(phone))
            data["client_phone"] = digits

        email = data.get("client_email")
        if email:
            data["client_email"] = email.strip().lower()

        return data

    def create(self, validated_data):
        """
        1. Extract items payload.
        2. If client_email or client_phone present -> find/create/update Client for this user.
        3. Populate invoice_data with client FK and snapshot fields.
        4. Call Invoice.create_with_items(...) which is atomic and efficient.
        """
        items_payload = validated_data.pop("items", [])
        user = self.context["request"].user

        # copy invoice_data so we don't mutate the original DRF internals
        invoice_data = dict(validated_data)

        # client fields from invoice payload (snapshot)
        c_email = invoice_data.get("client_email", None)
        c_phone = invoice_data.get("client_phone", None)
        c_name = invoice_data.get("client_name", None)
        c_address = invoice_data.get("client_address", None)

        # If either email or phone provided, try to find or create/update a Client
        client_instance = None
        if (c_email and c_email.strip()) or (c_phone and str(c_phone).strip()):
            # search by email first (case-insensitive)
            if c_email:
                client_instance = Client.objects.filter(created_by=user, email__iexact=c_email.strip().lower()).first()

            # if not found by email, try phone
            if not client_instance and c_phone:
                client_instance = Client.objects.filter(created_by=user, phone=str(c_phone)).first()

            # if found -> update missing fields if any provided
            if client_instance:
                updated = False
                if c_name and client_instance.name != c_name:
                    client_instance.name = c_name
                    updated = True
                if c_address and (not client_instance.address or client_instance.address != c_address):
                    client_instance.address = c_address
                    updated = True
                if c_email and (not client_instance.email or client_instance.email.lower() != c_email.lower()):
                    client_instance.email = c_email.lower()
                    updated = True
                if c_phone and (not client_instance.phone or client_instance.phone != str(c_phone)):
                    client_instance.phone = str(c_phone)
                    updated = True
                if updated:
                    client_instance.save(update_fields=["name", "address", "email", "phone"])
            else:
                # create a new client (allow missing name/email/phone per your rule)
                client_instance = Client.objects.create(
                    created_by=user,
                    name=c_name or "Unknown",
                    email=c_email.lower() if c_email else None,
                    phone=str(c_phone) if c_phone else None,
                    address=c_address or ""
                )

            # attach FK so invoice has a reference
            invoice_data["client"] = client_instance

            # ensure snapshot fields (keep them consistent)
            invoice_data["client_name"] = client_instance.name
            invoice_data["client_email"] = client_instance.email
            invoice_data["client_phone"] = client_instance.phone
            invoice_data["client_address"] = client_instance.address
        else:
            # No email or phone — do NOT create client; use provided snapshot fields only.
            # Ensure client snapshot fields exist (client_name already validated)
            invoice_data["client"] = None
            invoice_data["client_name"] = c_name
            invoice_data["client_email"] = c_email
            invoice_data["client_phone"] = c_phone
            invoice_data["client_address"] = c_address

        # Use the model helper to create invoice + items atomically
        invoice, created_items = Invoice.create_with_items(
            created_by=user,
            invoice_data=invoice_data,
            items_payload=items_payload,
        )

        return invoice
