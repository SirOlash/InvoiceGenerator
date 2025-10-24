from django.urls import path
from . import views

app_name = "billing"
urlpatterns = [
    path("clients/", views.client_list, name="client-list"),
    path("clients/<uuid:pk>/", views.client_detail, name="client-detail"),
]
