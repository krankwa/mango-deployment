from django.urls import path
from .views import (
    # Authentication
    register_api, login_api, logout_api,
    admin_login_api, admin_refresh_token,
    
    # ML Prediction
    predict_image, test_model_status,
    
    # Admin Dashboard APIs
    disease_statistics,
    classified_images_list,
    classified_images_detail,
    bulk_update_images,
    upload_image,
    export_dataset,
)
from django.conf import settings
from django.conf.urls.static import static

app_name = 'mangosense'

urlpatterns = [
    # Mobile app authentication endpoints
    path('register/', register_api, name='register_api'),
    path('login/', login_api, name='login_api'),
    path('logout/', logout_api, name='logout_api'),
    
    # Admin authentication endpoints for Angular
    path('auth/login/', admin_login_api, name='admin_login'),
    path('auth/refresh/', admin_refresh_token, name='admin_refresh'),
    
    # ML prediction endpoints
    path('predict/', predict_image, name='predict_image'),
    path('test-model/', test_model_status, name='test_model_status'),
    
    # Admin Dashboard APIs
    path('disease-statistics/', disease_statistics, name='disease_statistics'),
    path('classified-images/', classified_images_list, name='classified_images_list'),
    path('classified-images/<int:pk>/', classified_images_detail, name='classified_images_detail'),
    path('classified-images/bulk-update/', bulk_update_images, name='bulk_update_images'),
    path('upload-image/', upload_image, name='upload_image'),
    path('export-dataset/', export_dataset, name='export_dataset'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)