import re
from rest_framework import serializers
from .models import Client

PHONE_DIGITS_RE = re.compile(r"\D+")


def normalize_phone(raw):
    if not raw:
        return None
    digits = PHONE_DIGITS_RE.sub("", raw)
    if digits.startswith("234") and len(digits) > 3:
        digits = "0" + digits[3:]
    return digits

class ClientSerializer(serializers.ModelSerializer):
    # optional hook to ask the server to update the user's profile
    update_profile = serializers.BooleanField(write_only=True, required=False, default=False)
    profile = serializers.DictField(write_only=True, required=False)

    class Meta:
        model = Client
        fields = ["id", "name", "email", "phone", "address", "created_at", "updated_at", "update_profile", "profile"]
        read_only_fields = ["id", "created_at", "updated_at"]

        def __init__(self):
            self.context = None

        def validate(self, data):
            # normalize email and phone
            email = data.get("email")
            if email:
                data["email"] = email.strip().lower()

            phone = data.get("phone")
            if phone:
                data["phone"] = normalize_phone(phone)
            return data

        def create(self, validated_data):
            request = self.context.get("request")
            user = getattr(request, "user", None)

            # pop helper fields for profile update
            update_profile_flag = validated_data.pop("update_profile", False)
            profile_data = validated_data.pop("profile", None)

            # attempt to find existing client
            found = None
            email = validated_data.get("email")
            phone = validated_data.get("phone")

            if user is None or not user.is_authenticated:
                raise serializers.ValidationError("Authentication required to create a client.")

            if email:
                found = Client.objects.filter(created_by=user, email__iexact=email).first()

            if not found and phone:
                found = Client.objects.filter(created_by=user, phone=phone).first()

            if found:
                # update found client with any provided fields
                for k, v in validated_data.items():
                    setattr(found, k, v)
                found.save()
                client = found
            else:
                client = Client.objects.create(created_by=user, **validated_data)

                # optional: update user's profile if requested
            if update_profile_flag and profile_data:
                profile = getattr(user, "profile", None)
                if profile:
                    for k, v in profile_data.items():
                        if hasattr(profile, k):
                            setattr(profile, k, v)
                    profile.save()

            return client

        def update(self, instance, validated_data):
            # standard update for PUT/PATCH
            for k, v in validated_data.items():
                if k in ("update_profile", "profile"):
                    continue
                setattr(instance, k, v)
            instance.save()
            return instance