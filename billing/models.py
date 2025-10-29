import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

from django.conf import settings
from django.db import models, transaction

# constants
SUBTOTAL_DECIMAL_PLACES = 2
SUBTOTAL_MAX_DIGITS = 12
TOTAL_DECIMAL_PLACES = 0   # stored as whole number
TOTAL_MAX_DIGITS = 12
ROUNDING = ROUND_HALF_UP

class Client(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="clients"
    )
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("created_by", "email"), ("created_by", "phone")]
        ordering = ["-created_at"]

    def __str__(self):
        return self.name



class InvoiceNumberCounter(models.Model):
    """
    Counter per user per year to generate stable, sequential invoice numbers.
    Use select_for_update() in a transaction to avoid races.
    """
    year = models.PositiveIntegerField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    last = models.PositiveIntegerField(default=0)

    class Meta:
        # unique_together = ('created_by', 'invoice_number')
        indexes = [models.Index(fields=["year", "user"])]
        verbose_name = "Invoice number counter"
        verbose_name_plural = "Invoice number counters"

    def __str__(self):
        return f"user={self.user_id} year={self.year} last={self.last}"


class Invoice(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_SENT = "SENT"
    STATUS_PAID = "PAID"
    STATUS_OVERDUE = "OVERDUE"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SENT, "Sent"),
        (STATUS_PAID, "Paid"),
        (STATUS_OVERDUE, "Overdue"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    public_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="invoices"
    )

    client = models.ForeignKey(
        "billing.Client",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoices",
    )

    invoice_number = models.CharField(max_length=64, blank=True, null=True, unique=True)
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    currency = models.CharField(max_length=8, default="NGN")

    # denormalized seller fields (snapshot)
    seller_name = models.CharField(max_length=255, blank=True, null=True)
    seller_email = models.EmailField(blank=True, null=True)
    seller_phone = models.CharField(max_length=30, blank=True, null=True)
    seller_address = models.TextField(blank=True, null=True)
    seller_logo = models.CharField(max_length=1024, blank=True, null=True)

    # denormalized client snapshot
    client_name = models.CharField(max_length=255)
    client_email = models.EmailField(blank=True, null=True)
    client_phone = models.CharField(max_length=30, blank=True, null=True)
    client_address = models.TextField(blank=True, null=True)

    # amounts
    subtotal = models.DecimalField(
        max_digits=SUBTOTAL_MAX_DIGITS, decimal_places=SUBTOTAL_DECIMAL_PLACES, default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        max_digits=SUBTOTAL_MAX_DIGITS, decimal_places=SUBTOTAL_DECIMAL_PLACES, default=Decimal("0.00")
    )
    total = models.DecimalField(
        max_digits=TOTAL_MAX_DIGITS, decimal_places=TOTAL_DECIMAL_PLACES, default=Decimal("0")
    )

    notes = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to="invoices/images/", blank=True, null=True)

    payment_url = models.URLField(blank=True, null=True)
    pdf_file = models.FileField(upload_to="invoices/pdfs/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_by", "invoice_number"]),
            models.Index(fields=["public_uuid"]),
        ]

    def __str__(self):
        return f"{self.invoice_number or str(self.id)} - {self.client_name}"

    @staticmethod
    def _format_invoice_number(year: int, seq: int) -> str:
        """Format like INV-2025-0001"""
        return f"INV-{year}-{seq:04d}"

    @classmethod
    def _generate_invoice_number(cls, user):
        """
        Obtain a sequential invoice number for the current year and user.
        Must be called inside a transaction to be race-safe (select_for_update used).
        """
        year = date.today().year
        counter, created = InvoiceNumberCounter.objects.select_for_update().get_or_create(
            year=year,
            user=user,
            defaults={"last": 0},
        )
        counter.last += 1
        counter.save(update_fields=["last"])
        return cls._format_invoice_number(year, counter.last)

    def recompute_totals(self, save_after=True):
        """
        Single-pass totals recomputation:
        - subtotal: sum of item.compute_line_base() (2 decimal places)
        - discount_amount: invoice-level discount (kept as provided)
        - total: subtotal - discount, rounded to whole number (ROUND_HALF_UP)
        Call once after all items are created/updated.
        """
        items = self.items.all()
        subtotal = Decimal("0.00")
        quant_sub = Decimal((0, (1,), -SUBTOTAL_DECIMAL_PLACES))

        for item in items:
            subtotal += item.compute_line_base()

        subtotal = subtotal.quantize(quant_sub, rounding=ROUNDING)
        discount = (self.discount_amount or Decimal("0.00")).quantize(quant_sub, rounding=ROUNDING)

        total_before_round = (subtotal - discount)
        total_whole = total_before_round.quantize(Decimal("1"), rounding=ROUNDING)

        self.subtotal = subtotal
        self.discount_amount = discount
        self.total = total_whole

        if save_after:
            self.save(update_fields=["subtotal", "discount_amount", "total", "updated_at"])

        return {"subtotal": subtotal, "discount_amount": discount, "total": total_whole}

    @classmethod
    def create_with_items(cls, created_by, invoice_data: dict, items_payload: list):
        """
        Helper to create invoice + items in a single transaction safely.
        - created_by: user instance
        - invoice_data: dict for invoice fields (seller_name, client_name, etc.)
        - items_payload: list of dicts: { "item": "...", "quantity": "3", "rate": "600", "discount": "0.00" }
        Returns (invoice, created_items_queryset)
        """
        from decimal import Decimal

        with transaction.atomic():
            # create invoice instance (do not assign invoice_number yet)
            invoice = cls.objects.create(created_by=created_by, **invoice_data)

            # generate and set invoice_number in same transaction to prevent races
            invoice.invoice_number = cls._generate_invoice_number(created_by)
            invoice.save(update_fields=["invoice_number"])

            # prepare items and compute amount in Python
            items_to_create = []
            for it in items_payload:
                qty = Decimal(str(it.get("quantity", "0")))
                rate = Decimal(str(it.get("unit_price", it.get("rate", "0.00"))))
                discount = Decimal(str(it.get("discount", "0.00")))
                description = it.get("item") or it.get("description") or ""
                invoice_item = InvoiceItem(
                    invoice=invoice,
                    description=description,
                    quantity=qty,
                    unit_price=rate,
                    discount=discount,
                )
                invoice_item.amount = invoice_item.compute_amount()  # compute and cache before bulk_create
                items_to_create.append(invoice_item)

            # bulk create items (single DB insert)
            InvoiceItem.objects.bulk_create(items_to_create)

            # recompute invoice totals once and persist
            invoice.recompute_totals(save_after=True)

            return invoice, items_to_create


class InvoiceItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")

    description = models.TextField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=SUBTOTAL_MAX_DIGITS, decimal_places=SUBTOTAL_DECIMAL_PLACES, default=Decimal("0.00"))

    # line discount as absolute monetary amount
    discount = models.DecimalField(max_digits=SUBTOTAL_MAX_DIGITS, decimal_places=SUBTOTAL_DECIMAL_PLACES, default=Decimal("0.00"))

    # stored computed amount for convenience (2 decimal places)
    amount = models.DecimalField(max_digits=SUBTOTAL_MAX_DIGITS, decimal_places=SUBTOTAL_DECIMAL_PLACES, default=Decimal("0.00"))
    notes = models.TextField(blank=True, null=True)

    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.description[:40]} ({self.quantity} × {self.unit_price})"

    def compute_line_base(self):
        """
        Base amount after line discount, rounded to SUBTOTAL_DECIMAL_PLACES.
        """
        base = (self.quantity or Decimal("0.00")) * (self.unit_price or Decimal("0.00"))
        base_after_discount = (base - (self.discount or Decimal("0.00")))
        quant = Decimal((0, (1,), -SUBTOTAL_DECIMAL_PLACES))
        return base_after_discount.quantize(quant, rounding=ROUNDING)

    def compute_amount(self):
        """
        Total for this line (same as compute_line_base in this simplified model).
        """
        return self.compute_line_base()

    def save(self, *args, **kwargs):
        # Ensure amount is computed and saved. Do NOT trigger invoice.recompute_totals here.
        self.amount = self.compute_amount()
        super().save(*args, **kwargs)