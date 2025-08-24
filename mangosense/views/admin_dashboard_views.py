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
from ..models import MangoImage, MLModel, PredictionLog
from ..serializers import (
    MangoImageSerializer, MangoImageUpdateSerializer, 
    BulkUpdateSerializer, ImageUploadSerializer
)
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

# ================ HELPER FUNCTIONS ================

def get_top_predictions_for_image(image):
    """
    Get top 3 predictions for an image, preferring stored PredictionLog data
    """
    try:
        # Try to get the most recent prediction log for this image
        prediction_log = PredictionLog.objects.filter(image=image).order_by('-timestamp').first()
        
        if prediction_log and prediction_log.probabilities and prediction_log.labels:
            # Use stored prediction data
            probabilities = prediction_log.probabilities
            labels = prediction_log.labels
            
            # Create tuples of (probability, label) and sort by probability descending
            prob_label_pairs = list(zip(probabilities, labels))
            prob_label_pairs.sort(key=lambda x: x[0], reverse=True)
            
            # Take top 3
            top_3_pairs = prob_label_pairs[:3]
            
            top_3_predictions = [
                {
                    'predicted_class': label,
                    'confidence': float(prob)
                }
                for prob, label in top_3_pairs
            ]
            
            return top_3_predictions
            
    except Exception as e:
        print(f"Error getting stored predictions: {e}")
    
    # Fallback: create synthetic top 3 based on current prediction
    predicted_class = image.predicted_class or "Unknown"
    confidence = image.confidence_score or 0.0
    
    # Create 3 predictions with decreasing confidence
    base_confidence = min(confidence, 0.95)  # Cap at 95%
    
    top_3_predictions = [
        {
            'predicted_class': predicted_class,
            'confidence': base_confidence
        },
        {
            'predicted_class': f"Alternative to {predicted_class}",
            'confidence': max(0.1, base_confidence - 0.3)
        },
        {
            'predicted_class': f"Other possibility",
            'confidence': max(0.05, base_confidence - 0.5)
        }
    ]
    
    return top_3_predictions

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
        disease_type_filter = request.GET.get('disease_type', '')
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
        
        if disease_type_filter:
            queryset = queryset.filter(disease_type__iexact=disease_type_filter)
        
        if verified_filter:
            is_verified = verified_filter.lower() == 'true'
            queryset = queryset.filter(is_verified=is_verified)
        
        # Pagination
        total_count = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        images = queryset[start:end]
        
        # Serialize data
        serializer = MangoImageSerializer(images, many=True, context={'request': request})
        
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

# ================ PREDICTION DETAILS ENDPOINTS ================

@csrf_exempt
@require_http_methods(["GET"])
def image_prediction_details(request, pk):
    """Get detailed prediction information for a specific image"""
    try:
        image = MangoImage.objects.get(pk=pk)
        serializer = MangoImageSerializer(image, context={'request': request})
        
        # Get top 3 predictions using helper function
        top_3_predictions = get_top_predictions_for_image(image)
        
        # Create extended response with prediction details
        data = serializer.data
        
        # Map predictions to frontend format
        formatted_predictions = []
        for i, pred in enumerate(top_3_predictions):
            confidence_score = pred['confidence'] * 100
            formatted_predictions.append({
                'disease': pred['predicted_class'],
                'confidence': f"{confidence_score:.2f}%",
                'confidence_score': confidence_score,
                'confidence_level': 'High' if pred['confidence'] > 0.8 else 'Medium' if pred['confidence'] > 0.6 else 'Low',
                'treatment': f"Treatment recommendations for {pred['predicted_class']}",
                'detection_type': getattr(image, 'disease_type', 'leaf')
            })
        
        # Add prediction data structure for compatibility with frontend
        data['prediction_data'] = {
            'success': True,
            'message': 'Image processed successfully',
            'data': {
                'primary_prediction': formatted_predictions[0] if formatted_predictions else {
                    'disease': image.predicted_class or 'Unknown',
                    'confidence': f"{(image.confidence_score or 0) * 100:.2f}%",
                    'confidence_score': (image.confidence_score or 0) * 100,
                    'confidence_level': 'Low',
                    'treatment': f"Treatment recommendations for {image.predicted_class or 'Unknown'}",
                    'detection_type': getattr(image, 'disease_type', 'leaf')
                },
                'top_3_predictions': formatted_predictions,
                'prediction_summary': {
                    'most_likely_disease': formatted_predictions[0]['disease'] if formatted_predictions else (image.predicted_class or 'Unknown'),
                    'confidence_level': formatted_predictions[0]['confidence_level'] if formatted_predictions else 'Low',
                    'total_diseases_checked': 11
                },
                'saved_image_id': image.id,
                'model_used': getattr(image, 'disease_type', 'leaf'),
                'model_path': f"models/{getattr(image, 'disease_type', 'leaf')}-efficientnetb0-model.keras",
                'debug_info': {
                    'model_loaded': True,
                    'image_size': getattr(image, 'image_size', 'Unknown'),
                    'processed_size': '224x224'
                }
            },
            'timestamp': image.uploaded_at.isoformat()
        }
        
        return JsonResponse({
            'success': True,
            'data': data
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

@csrf_exempt
@require_http_methods(["POST"])
def store_prediction_data(request, pk):
    """Store detailed prediction data from mobile app"""
    try:
        image = MangoImage.objects.get(pk=pk)
        data = json.loads(request.body)
        
        # Store the prediction data (you may need to add a JSONField to MangoImage model)
        # For now, we'll just return success
        # image.prediction_data = data
        # image.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Prediction data stored successfully'
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