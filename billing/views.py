from django.db.models import QuerySet
from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Client
from .serializers import ClientSerializer


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def client_list(request):
    if request.method == "GET":
        qs = Client.objects.filter(created_by=request.user)
        serializer = ClientSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    # POST
    serializer = ClientSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        client = serializer.save()
        return Response(ClientSerializer(client, context={"request": request}).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def client_detail(request, pk):
    obj = get_object_or_404(Client, created_by=request.user, pk=pk)

    if request.method == "GET":
        serializer = ClientSerializer(obj, context={"request": request})
        return Response(serializer.data)

    if request.method in ("PUT", "PATCH"):
        partial = (request.method == "PATCH")
        serializer = ClientSerializer(obj, data=request.data, partial=partial, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    obj.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
