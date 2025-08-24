from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from PIL import Image
import numpy as np
import os
import gc
from ..models import MangoImage, MLModel, PredictionLog
from .utils import (
    get_client_ip, validate_image_file, get_disease_type,
    calculate_confidence_level, get_prediction_summary,
    log_prediction_activity, generate_unique_filename,
    create_api_response
)

import tensorflow as tf

# ML Configuration
IMG_SIZE = (224, 224)

# Separate class names for each model type (IMPROVED ORGANIZATION)
LEAF_CLASS_NAMES = [
    'Anthracnose', 'Bacterial Canker', 'Cutting Weevil', 'Die Back', 'Gall Midge',
    'Healthy', 'Powdery Mildew', 'Sooty Mold'
]

FRUIT_CLASS_NAMES = [
    'Anthracnose', 'Black Mold Rot', 'Healthy', 'Stem End Rot'
]

# Keep backward compatibility with old class_names (for any legacy code)
class_names = LEAF_CLASS_NAMES + ['Black Mold Rot', 'Stem End Rot']

# Treatment suggestions (complete list)
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
    try:
        img = Image.open(image_file).convert('RGB')
        original_size = img.size
        img = img.resize(IMG_SIZE)
        img_array = np.array(img)
        
        # CRITICAL FIX: Apply EfficientNet preprocessing then add batch dimension
        img_array = tf.keras.applications.efficientnet.preprocess_input(img_array)
        img_array = np.expand_dims(img_array, axis=0)
        
        return img_array, original_size
    except Exception as e:
        print(f"Error in preprocess_image: {e}")
        raise e


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def predict_image(request):
    """Handle image prediction from mobile Ionic app"""
    import time
    start_time = time.time()
    
    # Add debug logging
    print(f"DEBUG: Received prediction request from {get_client_ip(request)}")
    print(f"DEBUG: Files in request: {list(request.FILES.keys())}")
    print(f"DEBUG: Data in request: {request.data}")
    
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
        
        print(f"DEBUG: Processing image: {image_file.name}, size: {image_file.size}")

        # Validate image file using utils
        validation_errors = validate_image_file(image_file)
        if validation_errors:
            print(f"DEBUG: Validation errors: {validation_errors}")
            return JsonResponse(
                create_api_response(
                    success=False,
                    message='Invalid image file',
                    errors=validation_errors
                ),
                status=400
            )

        # Process image for prediction with error handling
        try:
            img_array, original_size = preprocess_image(image_file)
            print(f"DEBUG: Image preprocessed successfully, shape: {img_array.shape}")
        except Exception as preprocessing_error:
            print(f"DEBUG: Preprocessing error: {str(preprocessing_error)}")
            return JsonResponse(
                create_api_response(
                    success=False,
                    message='Image preprocessing failed',
                    errors=[str(preprocessing_error)]
                ),
                status=500
            )

        # Get prediction type
        detection_type = request.data.get('detection_type', 'leaf')
        print(f"DEBUG: Detection type: {detection_type}")

        # Choose model path and class names (IMPROVED LOGIC)
        if detection_type == 'fruit':
            model_path = FRUIT_MODEL_PATH
            model_used = 'fruit'
            model_class_names = FRUIT_CLASS_NAMES
        else:
            model_path = LEAF_MODEL_PATH
            model_used = 'leaf'
            model_class_names = LEAF_CLASS_NAMES

        print(f"DEBUG: Using model: {model_path}")
        print(f"DEBUG: Model exists: {os.path.exists(model_path)}")

        # Check if model file exists
        if not os.path.exists(model_path):
            return JsonResponse(
                create_api_response(
                    success=False,
                    message=f'Model file not found: {model_used}',
                    errors=[f'Model file {model_path} does not exist']
                ),
                status=500
            )

        # Load the model dynamically with error handling
        try:
            model = tf.keras.models.load_model(model_path)
            print(f"DEBUG: Model loaded successfully")
        except Exception as model_error:
            print(f"DEBUG: Model loading error: {str(model_error)}")
            return JsonResponse(
                create_api_response(
                    success=False,
                    message='Failed to load ML model',
                    errors=[str(model_error)]
                ),
                status=500
            )

        # Real ML prediction with error handling
        try:
            prediction = model.predict(img_array)
            prediction = np.array(prediction).flatten()
            print(f"DEBUG: Prediction successful, shape: {prediction.shape}")
        except Exception as prediction_error:
            print(f"DEBUG: Prediction error: {str(prediction_error)}")
            return JsonResponse(
                create_api_response(
                    success=False,
                    message='ML prediction failed',
                    errors=[str(prediction_error)]
                ),
                status=500
            )

        # Get prediction summary using utils
        prediction_summary = get_prediction_summary(prediction, model_class_names)

        # Set confidence threshold
        CONFIDENCE_THRESHOLD = 20.0

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
                disease_type=model_used,  # Use the actual model that was used for detection
                confidence_score=prediction_summary['primary_prediction']['confidence'] / 100,
                user=request.user if request.user.is_authenticated else None,
                image_size=f"{original_size[0]}x{original_size[1]}",
                client_ip=get_client_ip(request),
                notes=f"Predicted via mobile app with {prediction_summary['primary_prediction']['confidence']:.2f}% confidence"
            )
            log_prediction_activity(request.user, mango_image.id, prediction_summary)
            saved_image_id = mango_image.id
            print(f"DEBUG: Image saved to database with ID: {saved_image_id}")
        except Exception as e:
            print(f"Error saving image to database: {e}")
            saved_image_id = None

        # Memory cleanup
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
        try:
            probs_list = prediction.tolist() if hasattr(prediction, 'tolist') else list(map(float, prediction))
            labels_list = model_class_names
            response_time = time.time() - start_time
            PredictionLog.objects.create(
                image=mango_image if 'mango_image' in locals() else None,
                client_ip=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                response_time=response_time,
                probabilities=probs_list,
                labels=labels_list,
                prediction_summary=prediction_summary,
                raw_response=response_data
            )
        except Exception as e:
            print(f"DEBUG: Failed to save PredictionLog: {e}")

        print(f"DEBUG: Returning successful response for {prediction_summary['primary_prediction']['disease']}")
        return JsonResponse(
            create_api_response(
                success=True,
                data=response_data,
                message='Image processed successfully'
            )
        )

    except Exception as e:
        print(f"DEBUG: General error in predict_image: {str(e)}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        
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
            'leaf_model_path': LEAF_MODEL_PATH,
            'fruit_model_path': FRUIT_MODEL_PATH,
            'leaf_model_exists': os.path.exists(LEAF_MODEL_PATH),
            'fruit_model_exists': os.path.exists(FRUIT_MODEL_PATH),
            'leaf_class_names': LEAF_CLASS_NAMES,
            'fruit_class_names': FRUIT_CLASS_NAMES,
            'class_names': class_names,  # For backward compatibility
            'leaf_classes_count': len(LEAF_CLASS_NAMES),
            'fruit_classes_count': len(FRUIT_CLASS_NAMES),
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
                    'available_leaf_diseases': LEAF_CLASS_NAMES,
                    'available_fruit_diseases': FRUIT_CLASS_NAMES,
                    'available_diseases': class_names,  # For backward compatibility
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