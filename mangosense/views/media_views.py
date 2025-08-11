"""
Media serving views for production deployment
"""
import os
import mimetypes
from django.conf import settings
from django.http import HttpResponse, Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@csrf_exempt
@require_http_methods(["GET"])
def serve_media_file(request, file_path):
    """Serve media files in production when Django doesn't serve them automatically"""
    try:
        # Construct the full file path
        full_path = os.path.join(settings.MEDIA_ROOT, file_path)
        
        # Security check - ensure the file is within MEDIA_ROOT
        full_path = os.path.abspath(full_path)
        media_root = os.path.abspath(settings.MEDIA_ROOT)
        
        if not full_path.startswith(media_root):
            raise Http404("File not found")
        
        # Check if file exists
        if not os.path.exists(full_path):
            raise Http404("File not found")
        
        # Determine the content type
        content_type, _ = mimetypes.guess_type(full_path)
        if content_type is None:
            content_type = 'application/octet-stream'
        
        # Read and serve the file
        with open(full_path, 'rb') as file:
            response = HttpResponse(file.read(), content_type=content_type)
            response['Content-Length'] = os.path.getsize(full_path)
            # Add CORS headers for cross-origin requests
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET'
            response['Access-Control-Allow-Headers'] = 'Content-Type'
            return response
            
    except Exception as e:
        print(f"Error serving media file {file_path}: {str(e)}")
        raise Http404("File not found")


@csrf_exempt  
@require_http_methods(["GET"])
def test_media_access(request):
    """Test endpoint to check media file access"""
    try:
        media_root = settings.MEDIA_ROOT
        media_url = settings.MEDIA_URL
        
        # Check if media directory exists
        media_exists = os.path.exists(media_root)
        
        # List some files in mango_images
        mango_images_path = os.path.join(media_root, 'mango_images')
        mango_images_exist = os.path.exists(mango_images_path)
        
        files_list = []
        if mango_images_exist:
            files_list = os.listdir(mango_images_path)[:5]  # First 5 files
        
        # Test a specific image
        test_image = None
        if files_list:
            test_image_path = os.path.join(mango_images_path, files_list[0])
            test_image = {
                'filename': files_list[0],
                'exists': os.path.exists(test_image_path),
                'size': os.path.getsize(test_image_path) if os.path.exists(test_image_path) else 0,
                'url': f"{media_url}mango_images/{files_list[0]}",
                'direct_serve_url': f"/api/media/mango_images/{files_list[0]}"
            }
        
        return JsonResponse({
            'success': True,
            'data': {
                'media_root': media_root,
                'media_url': media_url,
                'media_directory_exists': media_exists,
                'mango_images_directory_exists': mango_images_exist,
                'sample_files': files_list,
                'test_image': test_image,
                'debug_info': {
                    'django_debug': settings.DEBUG,
                    'allowed_hosts': settings.ALLOWED_HOSTS,
                },
                'instructions': {
                    'message': 'Use /api/media/{file_path} to directly serve media files',
                    'example': '/api/media/mango_images/image_0RUOO8G.jpg'
                }
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error checking media access: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def debug_image_url(request, image_id):
    """Debug a specific image URL construction"""
    try:
        from ..models import MangoImage
        from ..serializers import MangoImageSerializer
        
        # Get the image
        image = MangoImage.objects.get(id=image_id)
        
        # Serialize the image
        serializer = MangoImageSerializer(image, context={'request': request})
        
        # Check if the actual file exists
        file_exists = os.path.exists(image.image.path) if image.image else False
        
        return JsonResponse({
            'success': True,
            'data': {
                'image_id': image_id,
                'serialized_data': serializer.data,
                'file_path': image.image.path if image.image else None,
                'file_exists': file_exists,
                'file_size': os.path.getsize(image.image.path) if file_exists else 0,
                'direct_serve_url': f"/api/media/{image.image.name}" if image.image else None
            }
        })
        
    except MangoImage.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Image not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error debugging image: {str(e)}'
        }, status=500)
