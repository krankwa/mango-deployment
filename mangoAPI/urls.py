from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({"status": "ok", "message": "Django app is running"})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', health_check, name='health_check'),  # Add this line
    path('api/', include('mangosense.urls')),  # Assuming your API routes are here
]
