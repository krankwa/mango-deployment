from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from PIL import Image
import numpy as np
import os
import gc
from ..models import MangoImage, MLModel
from .utils import (
    get_client_ip, validate_image_file, get_disease_type,
    calculate_confidence_level, get_prediction_summary,
    log_prediction_activity, generate_unique_filename,
    create_api_response
)

import tensorflow as tf

# ML Configuration
IMG_SIZE = (224, 224)
class_names = [
    'Anthracnose', 'Bacterial Canker', 'Cutting Weevil', 'Die Back', 'Gall Midge',
    'Healthy', 'Powdery Mildew', 'Sooty Mold', 'Black Mold Rot', 'Stem End Rot'
]

# Treatment suggestions
treatment_suggestions = {
    'Anthracnose': 'The diseased twigs should be pruned and burnt along with fallen leaves. Spraying twice with Carbendazim (Bavistin 0.1%) at 15 days interval during flowering controls blossom infection.',
    'Bacterial Canker': 'Three sprays of Streptocycline (0.01%) or Agrimycin-100 (0.01%) after first visual symptom at 10 day intervals are effective in controlling the disease.',
    'Cutting Weevil': 'Use recommended insecticides and remove infested plant material.',
    'Die Back': 'Pruning of the diseased twigs 2-3 inches below the affected portion and spraying Copper Oxychloride (0.3%) on infected trees controls the disease.',
    'Gall Midge': 'Remove and destroy infested fruits; use appropriate insecticides.',
    'Healthy': 'No treatment needed. Maintain good agricultural practices.',
    'Powdery Mildew': 'Alternate spraying of Wettable sulphur 0.2 per cent at 15 days interval are recommended for effective control of the disease.',
    'Sooty Mold': 'Pruning of affected branches and their prompt destruction followed by spraying of Wettasulf (0.2%) helps to control the disease.',
    'Black Mold Rot': 'Improve air circulation and apply fungicides as needed.',
    'Stem End Rot': 'Proper post-harvest handling and storage conditions are essential.'
}

# Model paths
LEAF_MODEL_PATH = os.path.join(settings.BASE_DIR, 'models', 'leaf-efficientnetb0-model.keras')
FRUIT_MODEL_PATH = os.path.join(settings.BASE_DIR, 'models', 'fruit-efficientnetb0-model.keras')



def preprocess_image(image_file):
    """Preprocess image for ML model prediction"""
    img = Image.open(image_file).convert('RGB')
    original_size = img.size
    img = img.resize(IMG_SIZE)
    img_array = np.array(img)
    
    # Uncomment when TensorFlow is available
    # img_array = tf.keras.applications.efficientnet.preprocess_input(img_array)
    img_array = np.expand_dims(img_array, axis=0)
    
    return img_array, original_size




@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def predict_image(request):
    """Handle image prediction from mobile Ionic app"""
    if 'image' not in request.FILES:
        return JsonResponse(
            create_api_response(
                success=False,
                message='No image uploaded',
                errors=['Image file is required']
            ),
            status=400
        )

    try:
        image_file = request.FILES['image']
        client_ip = get_client_ip(request)

        # Validate image file using utils
        validation_errors = validate_image_file(image_file)
        if validation_errors:
            return JsonResponse(
                create_api_response(
                    success=False,
                    message='Invalid image file',
                    errors=validation_errors
                ),
                status=400
            )

        # Process image for prediction
        img_array, original_size = preprocess_image(image_file)

        # Get prediction
        detection_type = request.data.get('detection_type', 'leaf')  # default to 'leaf' if not provided

        # Choose model path and class names
        if detection_type == 'fruit':
            model_path = FRUIT_MODEL_PATH
            model_used = 'fruit'
            model_class_names = [
                'Anthracnose', 'Black Mold Rot', 'Healthy', 'Stem end Rot'
            ]
        else:
            model_path = LEAF_MODEL_PATH
            model_used = 'leaf'
            model_class_names = [
                'Anthracnose', 'Bacterial Canker', 'Cutting Weevil', 'Die Back', 'Gall Midge',
                'Healthy', 'Powdery Mildew', 'Sooty Mold'
            ]

        # Load the model dynamically
        model = tf.keras.models.load_model(model_path)

        # Real ML prediction
        prediction = model.predict(img_array)
        prediction = np.array(prediction).flatten()

        # Get prediction summary using utils
        prediction_summary = get_prediction_summary(prediction, model_class_names)

        # Set confidence threshold
        CONFIDENCE_THRESHOLD = 50.0

        # Check if top prediction is below threshold
        if prediction_summary['primary_prediction']['confidence'] < CONFIDENCE_THRESHOLD:
            unknown_response = {
                'disease': 'Unknown',
                'confidence': f"{prediction_summary['primary_prediction']['confidence']:.2f}%",
                'confidence_score': prediction_summary['primary_prediction']['confidence'],
                'confidence_level': 'Low',
                'treatment': "The uploaded image could not be confidently classified. Please ensure the image is of a mango leaf or fruit and try again.",
                'detection_type': model_used
            }
            response_data = {
                'primary_prediction': unknown_response,
                'top_3_predictions': [],
                'prediction_summary': {
                    'most_likely': 'Unknown',
                    'confidence_level': 'Low',
                    'total_diseases_checked': len(model_class_names)
                },
                'saved_image_id': None,
                'model_used': model_used,
                'model_path': model_path,
                'debug_info': {
                    'model_loaded': True,
                    'image_size': original_size,
                    'processed_size': IMG_SIZE
                }
            }
            return JsonResponse(
                create_api_response(
                    success=True,
                    data=response_data,
                    message='Could not confidently classify the image. Please upload a clear image of a mango leaf or fruit.'
                )
            )

        # Add treatment suggestions
        for pred in prediction_summary['top_3']:
            pred['treatment'] = treatment_suggestions.get(pred['disease'], "No treatment information available.")
            pred['detection_type'] = model_used

        # Save to database
        try:
            image_file.seek(0)
            unique_filename = generate_unique_filename(image_file.name)
            mango_image = MangoImage.objects.create(
                image=image_file,
                original_filename=image_file.name,
                predicted_class=prediction_summary['primary_prediction']['disease'],
                disease_classification=prediction_summary['primary_prediction']['disease'],
                disease_type=get_disease_type(prediction_summary['primary_prediction']['disease']),
                confidence_score=prediction_summary['primary_prediction']['confidence'] / 100,
                user=request.user if request.user.is_authenticated else None,
                image_size=f"{original_size[0]}x{original_size[1]}",
                client_ip=get_client_ip(request),
                notes=f"Predicted via mobile app with {prediction_summary['primary_prediction']['confidence']:.2f}% confidence"
            )
            log_prediction_activity(request.user, mango_image.id, prediction_summary)
            saved_image_id = mango_image.id
        except Exception as e:
            print(f"Error saving image to database: {e}")
            saved_image_id = None

        gc.collect()

        response_data = {
            'primary_prediction': {
                'disease': prediction_summary['primary_prediction']['disease'],
                'confidence': f"{prediction_summary['primary_prediction']['confidence']:.2f}%",
                'confidence_score': prediction_summary['primary_prediction']['confidence'],
                'confidence_level': prediction_summary['confidence_level'],
                'treatment': treatment_suggestions.get(prediction_summary['primary_prediction']['disease'], "No treatment information available."),
                'detection_type': model_used
            },
            'top_3_predictions': prediction_summary['top_3'],
            'prediction_summary': {
                'most_likely': prediction_summary['primary_prediction']['disease'],
                'confidence_level': prediction_summary['confidence_level'],
                'total_diseases_checked': len(model_class_names)
            },
            'saved_image_id': saved_image_id,
            'model_used': model_used,
            'model_path': model_path,
            'debug_info': {
                'model_loaded': True,
                'image_size': original_size,
                'processed_size': IMG_SIZE
            }
        }

        return JsonResponse(
            create_api_response(
                success=True,
                data=response_data,
                message='Image processed successfully'
            )
        )

    except Exception as e:
        return JsonResponse(
            create_api_response(
                success=False,
                message='Prediction failed',
                errors=[str(e)]
            ),
            status=500
        )

@api_view(['GET'])
def test_model_status(request):
    """Test endpoint to check if model and class names are loaded properly"""
    try:
        # Get active model info from database
        active_model = MLModel.objects.filter(is_active=True).first()
        
        model_status = {
            'model_loaded': active_model is not None,
            'model_path': str(settings.MODEL_PATH) if hasattr(settings, 'MODEL_PATH') else 'Not set',
            'class_names': class_names,
            'class_names_count': len(class_names),
            'treatment_suggestions_count': len(treatment_suggestions),
            'active_model': {
                'name': active_model.name if active_model else None,
                'version': active_model.version if active_model else None,
                'accuracy': active_model.accuracy if active_model else None,
                'training_date': active_model.training_date if active_model else None
            } if active_model else None,
            'img_size': IMG_SIZE
        }
        
        database_stats = {
            'total_images': MangoImage.objects.count(),
            'healthy_images': MangoImage.objects.filter(disease_classification='Healthy').count(),
            'diseased_images': MangoImage.objects.exclude(disease_classification='Healthy').count(),
            'verified_images': MangoImage.objects.filter(is_verified=True).count()
        }
        
        return JsonResponse(
            create_api_response(
                success=True,
                data={
                    'model_status': model_status,
                    'available_diseases': class_names,
                    'database_stats': database_stats
                },
                message='Model status retrieved successfully'
            )
        )
        
    except Exception as e:
        return JsonResponse(
            create_api_response(
                success=False,
                message='Failed to get model status',
                errors=[str(e)]
            ),
            status=500
        )