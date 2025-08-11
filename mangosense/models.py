from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class MLModel(models.Model):
    """Model to store ML model metadata"""
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=20)
    file_path = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} v{self.version}"

class MangoImage(models.Model):
    """Model to store uploaded mango images and predictions"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    image = models.ImageField(upload_to='mango_images/')
    original_filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)  # Keep this one
    
    # Prediction results
    predicted_class = models.CharField(max_length=50, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)
    disease_type = models.CharField(max_length=20, blank=True)  # 'leaf' or 'fruit'
    
    # Additional fields needed for admin dashboard
    disease_classification = models.CharField(max_length=50, blank=True)
    # Remove upload_date since we already have uploaded_at
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_images')
    verified_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    # Metadata
    image_size = models.CharField(max_length=20, blank=True)
    processing_time = models.FloatField(null=True, blank=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.original_filename} - {self.predicted_class}"
    
    def save(self, *args, **kwargs):
        # Set disease_classification from predicted_class
        if self.predicted_class and not self.disease_classification:
            self.disease_classification = self.predicted_class
        super().save(*args, **kwargs)

class PredictionLog(models.Model):
    """Model to log prediction activities"""
    image = models.ForeignKey(MangoImage, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    client_ip = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    response_time = models.FloatField()
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"Prediction log for {self.image.original_filename}"

class UserConfirmation(models.Model):
    """Model to store user confirmations for AI predictions"""
    image = models.OneToOneField(MangoImage, on_delete=models.CASCADE, related_name='user_confirmation')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    is_correct = models.BooleanField()  # True = "Yes, this is a match", False = "No, this does not match"
    predicted_disease = models.CharField(max_length=50)  # What AI predicted
    user_feedback = models.TextField(blank=True)  # Optional user comments
    confidence_score = models.FloatField(null=True, blank=True)  # AI confidence when prediction was made
    confirmed_at = models.DateTimeField(auto_now_add=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    
    # Location data (if user consents)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_accuracy = models.FloatField(null=True, blank=True)
    location_consent_given = models.BooleanField(default=False)
    location_address = models.TextField(blank=True)  # Human-readable address
    
    class Meta:
        ordering = ['-confirmed_at']
    
    def __str__(self):
        status = "Confirmed" if self.is_correct else "Rejected"
        return f"{status}: {self.predicted_disease} for {self.image.original_filename}"

class UserProfile(models.Model):
    """Extended user profile"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Profile for {self.user.username}"

class Notification(models.Model):
    """Model to store notifications for admin dashboard"""
    NOTIFICATION_TYPES = [
        ('image_upload', 'Image Upload'),
        ('system', 'System'),
        ('alert', 'Alert'),
    ]
    
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='image_upload')
    title = models.CharField(max_length=200)
    message = models.TextField()
    related_image = models.ForeignKey(MangoImage, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # User who triggered the notification
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.user.username}"