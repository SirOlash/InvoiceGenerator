import re

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Profile

User = get_user_model()
PHONE_DIGITS_RE = re.compile(r'\D+')

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "date_joined", "is_staff", "is_active")
        read_only_fields = ("id", "date_joined", "is_staff", "is_active")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "email", "password")
        read_only_fields = ("id",)

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower() if value else value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        email = validated_data.pop("email")
        user = User.objects.create_user(email=email, password=password, **validated_data)
        return user


class ProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Profile
        fields = (
            "id",
            "email",
            "full_name",
            "business_name",
            "address",
            "phone",
            "logo",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "email", "created_at", "updated_at")

    def validate_phone(self, value):
        if not value:
            return value
        digits = PHONE_DIGITS_RE.sub("", value)
        if len(digits) == 10:
            normalized = "0" + digits
        elif len(digits) == 11 and digits.startswith("0"):
            normalized = digits
        elif len(digits) == 13 and digits.startswith("234"):
            normalized = "0" + digits[3:]
        else:
            raise serializers.ValidationError(
                "Enter a valid phone Number"
            )
        qs = Profile.objects.filter(phone=normalized)
        instance = getattr(self, "instance", None)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A profile using this phone number already exists.")

        return normalized

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)

    def create(self, validated_data):
        return super().create(validated_data)

