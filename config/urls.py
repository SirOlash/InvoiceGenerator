
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", RedirectView.as_view(url="/api/", permanent=False)),
    path("api/", include("billing.urls", namespace="billing")),
    path("api/auth/", include("accounts.urls")),

]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
