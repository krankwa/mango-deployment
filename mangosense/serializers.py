from rest_framework import serializers
from django.contrib.auth.models import User
from .models import MangoImage, MLModel, PredictionLog, UserProfile

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'date_joined']
        read_only_fields = ['id', 'date_joined']

class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = UserProfile
        fields = ['user', 'address', 'phone', 'created_at']
        read_only_fields = ['created_at']

class MangoImageSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = MangoImage
        fields = [
            'id', 'user', 'image', 'original_filename', 'uploaded_at',
            'predicted_class', 'confidence_score', 'disease_type',
            'image_size', 'processing_time', 'client_ip'
        ]
        read_only_fields = [
            'id', 'uploaded_at', 'predicted_class', 'confidence_score',
            'disease_type', 'image_size', 'processing_time', 'client_ip'
        ]

class MangoImageUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating MangoImage records"""
    class Meta:
        model = MangoImage
        fields = [
            'predicted_class', 'confidence_score', 'disease_type',
            'image_size', 'processing_time', 'client_ip'
        ]
        # All fields are optional for updates
        extra_kwargs = {
            'predicted_class': {'required': False},
            'confidence_score': {'required': False},
            'disease_type': {'required': False},
            'image_size': {'required': False},
            'processing_time': {'required': False},
            'client_ip': {'required': False},
        }

class BulkUpdateSerializer(serializers.Serializer):
    """Serializer for bulk updating multiple images"""
    image_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="List of image IDs to update"
    )
    updates = serializers.DictField(
        help_text="Dictionary of fields to update"
    )
    
    def validate_image_ids(self, value):
        """Validate that all image IDs exist"""
        existing_ids = MangoImage.objects.filter(id__in=value).values_list('id', flat=True)
        missing_ids = set(value) - set(existing_ids)
        if missing_ids:
            raise serializers.ValidationError(f"Images with IDs {list(missing_ids)} do not exist")
        return value
    
    def validate_updates(self, value):
        """Validate update fields"""
        allowed_fields = [
            'predicted_class', 'confidence_score', 'disease_type',
            'image_size', 'processing_time', 'client_ip', 'is_verified'
        ]
        
        invalid_fields = set(value.keys()) - set(allowed_fields)
        if invalid_fields:
            raise serializers.ValidationError(f"Invalid fields: {list(invalid_fields)}")
        
        return value

class MLModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = MLModel
        fields = ['id', 'name', 'version', 'file_path', 'created_at', 'is_active']
        read_only_fields = ['id', 'created_at']

class PredictionLogSerializer(serializers.ModelSerializer):
    image = MangoImageSerializer(read_only=True)
    
    class Meta:
        model = PredictionLog
        fields = ['id', 'image', 'timestamp', 'client_ip', 'user_agent', 'response_time']
        read_only_fields = ['id', 'timestamp']

class ImageUploadSerializer(serializers.Serializer):
    """Serializer for image upload endpoint"""
    image = serializers.ImageField()
    
    def validate_image(self, value):
        # Validate image size (max 5MB)
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Image size cannot exceed 5MB")
        
        # Validate image format
        allowed_formats = ['JPEG', 'JPG', 'PNG']
        if value.image.format not in allowed_formats:
            raise serializers.ValidationError("Only JPEG and PNG images are allowed")
        
        return value