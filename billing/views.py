from rest_framework import viewsets, permissions
from rest_framework.decorators import api_view

from .models import Client
from .serializers import ClientSerializer

@api_view(['GET', 'POST'])
def client_list(request):
    if request.method == 'GET':


# Create your views here.
