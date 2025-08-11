from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from django.utils import timezone
from ..models import MangoImage, UserConfirmation
from .utils import get_client_ip, create_api_response
import json

@api_view(['POST'])
@permission_classes([AllowAny])
def save_user_confirmation(request):
    """Save user confirmation for AI prediction"""
    try:
        data = request.data
        
        # Required fields
        image_id = data.get('image_id')
        is_correct = data.get('is_correct')
        predicted_disease = data.get('predicted_disease')
        
        if image_id is None or is_correct is None or not predicted_disease:
            return JsonResponse(
                create_api_response(
                    success=False,
                    message='Missing required fields',
                    errors=['image_id, is_correct, and predicted_disease are required']
                ),
                status=400
            )
        
        # Get the image
        try:
            image = MangoImage.objects.get(id=image_id)
        except MangoImage.DoesNotExist:
            return JsonResponse(
                create_api_response(
                    success=False,
                    message='Image not found',
                    errors=[f'No image found with ID {image_id}']
                ),
                status=404
            )
        
        # Check if confirmation already exists
        existing_confirmation = UserConfirmation.objects.filter(image=image).first()
        if existing_confirmation:
            return JsonResponse(
                create_api_response(
                    success=False,
                    message='Confirmation already exists for this image',
                    errors=['This image has already been confirmed by user']
                ),
                status=400
            )
        
        # Create confirmation record
        confirmation_data = {
            'image': image,
            'user': request.user if request.user.is_authenticated else None,
            'is_correct': bool(is_correct),
            'predicted_disease': predicted_disease,
            'user_feedback': data.get('user_feedback', ''),
            'confidence_score': data.get('confidence_score'),
            'client_ip': get_client_ip(request),
        }
        
        # Handle location data if provided and consent given
        location_consent = data.get('location_consent_given', False)
        if location_consent:
            confirmation_data.update({
                'location_consent_given': True,
                'latitude': data.get('latitude'),
                'longitude': data.get('longitude'),
                'location_accuracy': data.get('location_accuracy'),
                'location_address': data.get('location_address', ''),
            })
        
        confirmation = UserConfirmation.objects.create(**confirmation_data)
        
        return JsonResponse(
            create_api_response(
                success=True,
                data={
                    'confirmation_id': confirmation.id,
                    'image_id': image.id,
                    'is_correct': confirmation.is_correct,
                    'predicted_disease': confirmation.predicted_disease,
                    'confirmed_at': confirmation.confirmed_at.isoformat(),
                    'location_saved': confirmation.location_consent_given
                },
                message='User confirmation saved successfully'
            )
        )
        
    except Exception as e:
        return JsonResponse(
            create_api_response(
                success=False,
                message='Failed to save confirmation',
                errors=[str(e)]
            ),
            status=500
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_confirmations(request):
    """Get user confirmations for admin dashboard"""
    try:
        # Get query parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        filter_type = request.GET.get('filter', 'all')  # all, confirmed, rejected
        user_id = request.GET.get('user_id')
        disease = request.GET.get('disease')
        
        # Base queryset
        queryset = UserConfirmation.objects.select_related('image', 'user').all()
        
        # Apply filters
        if filter_type == 'confirmed':
            queryset = queryset.filter(is_correct=True)
        elif filter_type == 'rejected':
            queryset = queryset.filter(is_correct=False)
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        if disease:
            queryset = queryset.filter(predicted_disease__icontains=disease)
        
        # Pagination
        total_count = queryset.count()
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        confirmations = queryset[start_index:end_index]
        
        # Serialize data
        confirmation_data = []
        for conf in confirmations:
            confirmation_data.append({
                'id': conf.id,
                'image': {
                    'id': conf.image.id,
                    'filename': conf.image.original_filename,
                    'image_url': conf.image.image.url if conf.image.image else None,
                    'uploaded_at': conf.image.uploaded_at.isoformat(),
                },
                'user': {
                    'id': conf.user.id if conf.user else None,
                    'username': conf.user.username if conf.user else 'Anonymous',
                    'email': conf.user.email if conf.user else '',
                    'full_name': f"{conf.user.first_name} {conf.user.last_name}".strip() if conf.user else 'Anonymous'
                },
                'is_correct': conf.is_correct,
                'predicted_disease': conf.predicted_disease,
                'user_feedback': conf.user_feedback,
                'confidence_score': conf.confidence_score,
                'confirmed_at': conf.confirmed_at.isoformat(),
                'location': {
                    'consent_given': conf.location_consent_given,
                    'latitude': conf.latitude,
                    'longitude': conf.longitude,
                    'accuracy': conf.location_accuracy,
                    'address': conf.location_address
                } if conf.location_consent_given else None,
                'client_ip': conf.client_ip
            })
        
        # Calculate statistics
        stats = {
            'total_confirmations': total_count,
            'confirmed_count': UserConfirmation.objects.filter(is_correct=True).count(),
            'rejected_count': UserConfirmation.objects.filter(is_correct=False).count(),
            'accuracy_rate': 0
        }
        
        if stats['total_confirmations'] > 0:
            stats['accuracy_rate'] = round(
                (stats['confirmed_count'] / stats['total_confirmations']) * 100, 2
            )
        
        return JsonResponse(
            create_api_response(
                success=True,
                data={
                    'confirmations': confirmation_data,
                    'pagination': {
                        'page': page,
                        'page_size': page_size,
                        'total_count': total_count,
                        'total_pages': (total_count + page_size - 1) // page_size,
                        'has_next': end_index < total_count,
                        'has_previous': page > 1
                    },
                    'statistics': stats
                },
                message='User confirmations retrieved successfully'
            )
        )
        
    except Exception as e:
        return JsonResponse(
            create_api_response(
                success=False,
                message='Failed to get confirmations',
                errors=[str(e)]
            ),
            status=500
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_confirmation_statistics(request):
    """Get detailed statistics about user confirmations"""
    try:
        # Overall stats
        total_confirmations = UserConfirmation.objects.count()
        confirmed_count = UserConfirmation.objects.filter(is_correct=True).count()
        rejected_count = UserConfirmation.objects.filter(is_correct=False).count()
        
        # Disease-wise accuracy
        disease_stats = []
        diseases = UserConfirmation.objects.values('predicted_disease').distinct()
        
        for disease_data in diseases:
            disease = disease_data['predicted_disease']
            disease_total = UserConfirmation.objects.filter(predicted_disease=disease).count()
            disease_confirmed = UserConfirmation.objects.filter(
                predicted_disease=disease, is_correct=True
            ).count()
            disease_rejected = UserConfirmation.objects.filter(
                predicted_disease=disease, is_correct=False
            ).count()
            
            accuracy = (disease_confirmed / disease_total * 100) if disease_total > 0 else 0
            
            disease_stats.append({
                'disease': disease,
                'total_predictions': disease_total,
                'confirmed': disease_confirmed,
                'rejected': disease_rejected,
                'accuracy_rate': round(accuracy, 2)
            })
        
        # Sort by total predictions (most common diseases first)
        disease_stats.sort(key=lambda x: x['total_predictions'], reverse=True)
        
        # User engagement stats
        users_with_confirmations = UserConfirmation.objects.filter(
            user__isnull=False
        ).values('user').distinct().count()
        
        anonymous_confirmations = UserConfirmation.objects.filter(
            user__isnull=True
        ).count()
        
        # Location data stats
        confirmations_with_location = UserConfirmation.objects.filter(
            location_consent_given=True
        ).count()
        
        overall_accuracy = (confirmed_count / total_confirmations * 100) if total_confirmations > 0 else 0
        
        return JsonResponse(
            create_api_response(
                success=True,
                data={
                    'overall_statistics': {
                        'total_confirmations': total_confirmations,
                        'confirmed_count': confirmed_count,
                        'rejected_count': rejected_count,
                        'overall_accuracy': round(overall_accuracy, 2),
                        'users_with_confirmations': users_with_confirmations,
                        'anonymous_confirmations': anonymous_confirmations,
                        'confirmations_with_location': confirmations_with_location
                    },
                    'disease_statistics': disease_stats,
                    'location_consent_rate': round(
                        (confirmations_with_location / total_confirmations * 100), 2
                    ) if total_confirmations > 0 else 0
                },
                message='Confirmation statistics retrieved successfully'
            )
        )
        
    except Exception as e:
        return JsonResponse(
            create_api_response(
                success=False,
                message='Failed to get statistics',
                errors=[str(e)]
            ),
            status=500
        )
