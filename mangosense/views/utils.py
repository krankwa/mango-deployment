from django.http import JsonResponse
from django.utils import timezone  # Add this import
import json
import os
import uuid
from PIL import Image

def get_client_ip(request):
    """Get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def validate_password_strength(password):
    """Validate password strength - minimum 8 characters"""
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not any(char.isdigit() for char in password):
        errors.append("Password must contain at least one digit.")
    if not any(char.isupper() for char in password):
        errors.append("Password must contain at least one uppercase letter.")
    return errors

def validate_email_format(email):
    """Basic email validation"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# Additional utility functions for MangoSense

def validate_image_file(image_file):
    """Validate uploaded image file"""
    errors = []
    
    # Check file size (max 10MB)
    if image_file.size > 10 * 1024 * 1024:
        errors.append("Image size must be less than 10MB")
    
    # Check file type
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
    if image_file.content_type not in allowed_types:
        errors.append("Only JPEG, PNG, and WebP images are allowed")
    
    # Check file extension
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    file_extension = image_file.name.lower().split('.')[-1]
    if f'.{file_extension}' not in allowed_extensions:
        errors.append("Invalid file extension")
    
    return errors

def get_disease_type(disease_name):
    """Determine if disease affects leaf or fruit"""
    fruit_diseases = ['Alternaria', 'Black Mould Rot', 'Stem End Rot']
    return 'fruit' if disease_name in fruit_diseases else 'leaf'

def calculate_confidence_level(confidence_score):
    """Convert confidence score to human readable level"""
    if confidence_score >= 0.8:
        return 'High'
    elif confidence_score >= 0.6:
        return 'Medium'
    elif confidence_score >= 0.4:
        return 'Low'
    else:
        return 'Very Low'

def format_file_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"

def sanitize_filename(filename):
    """Sanitize filename for safe storage"""
    import re
    # Remove special characters and replace spaces with underscores
    filename = re.sub(r'[^\w\s-]', '', filename)
    filename = re.sub(r'[-\s]+', '_', filename)
    return filename

def get_prediction_summary(predictions, class_names):
    """Create a summary of ML predictions"""
    import numpy as np
    
    # Get top 3 predictions
    top_3_indices = np.argsort(predictions)[-3:][::-1]
    
    summary = {
        'primary_prediction': {
            'disease': class_names[top_3_indices[0]],
            'confidence': float(predictions[top_3_indices[0]]) * 100
        },
        'top_3': [],
        'confidence_level': calculate_confidence_level(predictions[top_3_indices[0]])
    }
    
    for i, idx in enumerate(top_3_indices):
        confidence = float(predictions[idx]) * 100
        summary['top_3'].append({
            'rank': i + 1,
            'disease': class_names[idx],
            'confidence': round(confidence, 2),
            'confidence_formatted': f"{confidence:.2f}%"
        })
    
    return summary

def log_prediction_activity(user, image_id, prediction_result):
    """Log prediction activity for analytics"""
    from django.utils import timezone
    import logging
    
    logger = logging.getLogger('mangosense.predictions')
    
    log_data = {
        'user_id': user.id if user and user.is_authenticated else None,
        'image_id': image_id,
        'prediction': prediction_result.get('primary_prediction', {}).get('disease'),
        'confidence': prediction_result.get('primary_prediction', {}).get('confidence'),
        'timestamp': timezone.now().isoformat(),
        'ip_address': getattr(user, 'ip_address', None)
    }
    
    logger.info(f"Prediction logged: {log_data}")
    return log_data

def validate_admin_permissions(user):
    """Validate if user has admin permissions"""
    if not user or not user.is_authenticated:
        return False, "Authentication required"
    
    if not user.is_staff:
        return False, "Admin permissions required"
    
    return True, "Valid admin user"

def paginate_queryset(queryset, page_number, page_size=20):
    """Paginate queryset with error handling"""
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    paginator = Paginator(queryset, page_size)
    
    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        page = paginator.page(1)
    except EmptyPage:
        page = paginator.page(paginator.num_pages)
    
    return {
        'results': page.object_list,
        'pagination': {
            'current_page': page.number,
            'total_pages': paginator.num_pages,
            'total_items': paginator.count,
            'has_next': page.has_next(),
            'has_previous': page.has_previous(),
            'next_page': page.next_page_number() if page.has_next() else None,
            'previous_page': page.previous_page_number() if page.has_previous() else None
        }
    }

def create_api_response(success=True, message="", data=None, errors=None, error_code=None, status_code=200):
    """Create standardized API response"""
    response_data = {
        'success': success,
        'message': message,
        'data': data or {},
        'timestamp': timezone.now().isoformat()  # timezone is now imported
    }
    
    if errors:
        response_data['errors'] = errors
    
    if error_code:
        response_data['error_code'] = error_code
    
    return response_data

def generate_unique_filename(original_filename):
    """Generate unique filename to avoid conflicts"""
    import uuid
    import os
    
    # Get file extension
    name, ext = os.path.splitext(original_filename)
    
    # Generate unique filename
    unique_id = str(uuid.uuid4())[:8]
    safe_name = sanitize_filename(name)
    
    return f"{safe_name}_{unique_id}{ext}"

def validate_date_range(start_date, end_date):
    """Validate date range for filtering"""
    from datetime import datetime
    
    errors = []
    
    if start_date and end_date:
        try:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            
            if start > end:
                errors.append("Start date must be before end date")
            
            # Check if date range is not too wide (max 1 year)
            if (end - start).days > 365:
                errors.append("Date range cannot exceed 1 year")
                
        except ValueError:
            errors.append("Invalid date format")
    
    return errors

def get_system_stats():
    """Get system statistics for monitoring"""
    from ..models import MangoImage, MLModel
    from django.contrib.auth.models import User
    import psutil
    import os
    
    stats = {
        'database': {
            'total_images': MangoImage.objects.count(),
            'verified_images': MangoImage.objects.filter(is_verified=True).count(),
            'total_users': User.objects.count(),
            'active_models': MLModel.objects.filter(is_active=True).count()
        },
        'system': {
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:').percent
        }
    }
    
    return stats