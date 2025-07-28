from rest_framework import status, generics, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
import json
import traceback
from ..models import MangoImage, MLModel
from ..serializers import (
    MangoImageSerializer, MangoImageUpdateSerializer, 
    BulkUpdateSerializer, ImageUploadSerializer
)
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

# ================ PAGINATION ================

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

# ================ DISEASE STATISTICS VIEW ================

@csrf_exempt
@require_http_methods(["GET"])
def disease_statistics(request):
    """Get disease statistics for dashboard"""
    try:
        # Get total counts
        total_images = MangoImage.objects.count()
        
        # Count healthy vs diseased based on predicted_class
        healthy_images = MangoImage.objects.filter(
            Q(predicted_class__icontains='healthy') | 
            Q(predicted_class__icontains='Healthy')
        ).count()
        
        diseased_images = total_images - healthy_images
        
        # Count by disease type (leaf vs fruit)
        leaf_images = MangoImage.objects.filter(
            predicted_class__icontains='Leaf'
        ).count()
        
        fruit_images = MangoImage.objects.filter(
            predicted_class__icontains='Fruit'
        ).count()
        
        # Get disease breakdown by predicted_class
        diseases_breakdown = {}
        disease_counts = MangoImage.objects.values('predicted_class').annotate(
            count=Count('id')
        ).order_by('-count')
        
        for disease in disease_counts:
            diseases_breakdown[disease['predicted_class']] = disease['count']
        
        # Recent uploads (last 7 days) - using uploaded_at instead of upload_date
        week_ago = timezone.now() - timedelta(days=7)
        recent_uploads = MangoImage.objects.filter(
            uploaded_at__gte=week_ago
        ).count()
        
        # Monthly statistics
        month_ago = timezone.now() - timedelta(days=30)
        monthly_uploads = MangoImage.objects.filter(
            uploaded_at__gte=month_ago
        ).count()
        
        data = {
            'total_images': total_images,
            'healthy_images': healthy_images,
            'diseased_images': diseased_images,
            'leaf_images': leaf_images,
            'fruit_images': fruit_images,
            'diseases_breakdown': diseases_breakdown,
            'recent_uploads': recent_uploads,
            'monthly_uploads': monthly_uploads,
            'verification_stats': {
                'verified': MangoImage.objects.filter(is_verified=True).count(),
                'unverified': MangoImage.objects.filter(is_verified=False).count(),
            }
        }
        
        return JsonResponse({
            'success': True,
            'data': data
        })
        
    except Exception as e:
        print(f"Error in disease_statistics: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)

# ================ CLASSIFIED IMAGES VIEWS ================

@csrf_exempt
@require_http_methods(["GET"])
def classified_images_list(request):
    """Get paginated list of classified images"""
    try:
        # Get query parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        search = request.GET.get('search', '')
        disease_filter = request.GET.get('disease', '')
        verified_filter = request.GET.get('verified', '')
        
        # Build query
        queryset = MangoImage.objects.all().order_by('-uploaded_at')  # Use uploaded_at
        
        # Apply filters
        if search:
            queryset = queryset.filter(
                Q(original_filename__icontains=search) |
                Q(predicted_class__icontains=search)
            )
        
        if disease_filter:
            queryset = queryset.filter(predicted_class__icontains=disease_filter)
        
        if verified_filter:
            is_verified = verified_filter.lower() == 'true'
            queryset = queryset.filter(is_verified=is_verified)
        
        # Pagination
        total_count = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        images = queryset[start:end]
        
        # Serialize data
        serializer = MangoImageSerializer(images, many=True)
        
        return JsonResponse({
            'success': True,
            'data': {
                'images': serializer.data,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total_count': total_count,
                    'total_pages': (total_count + page_size - 1) // page_size,
                    'has_next': end < total_count,
                    'has_previous': page > 1
                }
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)

@csrf_exempt 
@require_http_methods(["GET", "PUT", "DELETE"])
def classified_images_detail(request, pk):
    """Get, update, or delete a specific classified image"""
    try:
        image = MangoImage.objects.get(pk=pk)
        
        if request.method == 'GET':
            serializer = MangoImageSerializer(image)
            return JsonResponse({
                'success': True,
                'data': serializer.data
            })
            
        elif request.method == 'PUT':
            data = json.loads(request.body)
            serializer = MangoImageUpdateSerializer(image, data=data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                return JsonResponse({
                    'success': True,
                    'message': 'Image updated successfully',
                    'data': MangoImageSerializer(image).data
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': serializer.errors
                }, status=400)
                
        elif request.method == 'DELETE':
            image.delete()
            return JsonResponse({
                'success': True,
                'message': 'Image deleted successfully'
            })
            
    except MangoImage.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Image not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)

# ================ MISSING VIEWS ================

@csrf_exempt
@require_http_methods(["POST"])
def bulk_update_images(request):
    """Bulk update multiple images"""
    try:
        data = json.loads(request.body)
        serializer = BulkUpdateSerializer(data=data)
        
        if serializer.is_valid():
            image_ids = serializer.validated_data['image_ids']
            updates = serializer.validated_data['updates']
            
            # Update images
            updated_count = MangoImage.objects.filter(
                id__in=image_ids
            ).update(**updates)
            
            return JsonResponse({
                'success': True,
                'message': f'Successfully updated {updated_count} images',
                'updated_count': updated_count
            })
        else:
            return JsonResponse({
                'success': False,
                'error': serializer.errors
            }, status=400)
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def upload_image(request):
    """Upload a new image"""
    try:
        serializer = ImageUploadSerializer(data=request.FILES)
        
        if serializer.is_valid():
            image_file = serializer.validated_data['image']
            
            # Create new MangoImage instance
            mango_image = MangoImage.objects.create(
                image=image_file,
                original_filename=image_file.name,
                user=request.user if request.user.is_authenticated else None
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Image uploaded successfully',
                'data': MangoImageSerializer(mango_image).data
            })
        else:
            return JsonResponse({
                'success': False,
                'error': serializer.errors
            }, status=400)
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def export_dataset(request):
    """Export dataset"""
    try:
        # Get all images
        images = MangoImage.objects.all()
        
        # Create export data
        export_data = []
        for image in images:
            export_data.append({
                'id': image.id,
                'filename': image.original_filename,
                'predicted_class': image.predicted_class,
                'confidence_score': image.confidence_score,
                'uploaded_at': image.uploaded_at.isoformat(),
                'is_verified': image.is_verified
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'images': export_data,
                'total_count': len(export_data)
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)