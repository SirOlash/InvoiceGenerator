from rest_framework import routers
from .views import ClientViewSet
from django.urls import path, include

router = routers.DefaultRouter()
router.register('clients', ClientViewSet, basename="client")