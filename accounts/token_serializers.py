from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = User.USERNAME_FIELD

    def validate(self, attrs):
        # SimpleJWT expects the username field in attrs; allow clients to send "email"
        raw_email = attrs.get("email") or attrs.get(self.username_field)
        password = attrs.get("password")
        if raw_email:
            attrs[self.username_field] = raw_email
        return super().validate(attrs)