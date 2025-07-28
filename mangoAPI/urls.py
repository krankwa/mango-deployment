from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
import os

def health_check(request):
    return JsonResponse({
        "status": "ok", 
        "message": "Django app is running",
        "port": os.environ.get('PORT', 'Not set'),
        "debug": os.environ.get('DEBUG', 'Not set')
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', health_check, name='health_check'),
    path('api/', include('mangosense.urls')),
]
