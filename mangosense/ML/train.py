import tensorflow as tf
import os
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay, classification_report, accuracy_score
from django.conf import settings

class MangoModelTrainer:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.path.join(settings.BASE_DIR, 'datasets', 'split-mango')
        self.train_dir = os.path.join(self.base_dir, 'train')
        self.val_dir = os.path.join(self.base_dir, 'val')
        self.test_dir = os.path.join(self.base_dir, 'test')
        self.model_path = os.path.join(settings.BASE_DIR, 'ml_models', 'efficientnetb0-mango.keras')
        
    def count_images_per_class(self):
        """Count images in each class in the training directory"""
        class_counts = {}
        for cls in os.listdir(self.train_dir):
            count = len(os.listdir(os.path.join(self.train_dir, cls)))
            class_counts[cls] = count
            print(f"{cls}: {count} images")
        return class_counts
    
    def load_datasets(self):
        """Load training, validation, and test datasets"""
        self.train_dataset = tf.keras.preprocessing.image_dataset_from_directory(
            self.train_dir,
            image_size=(224, 224),
            batch_size=32,
            label_mode='categorical',
            shuffle=True
        )

        self.val_dataset = tf.keras.preprocessing.image_dataset_from_directory(
            self.val_dir,
            image_size=(224, 224),
            batch_size=32,
            label_mode='categorical'
        )

        self.test_dataset = tf.keras.preprocessing.image_dataset_from_directory(
            self.test_dir,
            image_size=(224, 224),
            batch_size=32,
            label_mode='categorical'
        )
        
        self.num_classes = len(self.train_dataset.class_names)
        self.class_names = self.train_dataset.class_names
        print(f"Classes: {self.class_names}")
        return self.train_dataset, self.val_dataset, self.test_dataset
    
    def create_model(self):
        """Create the EfficientNetB0 model"""
        # Data augmentation pipeline
        data_augmentation = tf.keras.Sequential([
            tf.keras.layers.RandomFlip("horizontal"),
            tf.keras.layers.RandomRotation(0.1),
            tf.keras.layers.RandomZoom(0.1),
            tf.keras.layers.RandomContrast(0.1),
        ])

        # Build EfficientNetB0 model
        base_model = tf.keras.applications.EfficientNetB0(
            include_top=False,
            input_shape=(224, 224, 3),
            weights='imagenet',
            pooling='avg'
        )
        base_model.trainable = False

        inputs = tf.keras.Input(shape=(224, 224, 3))
        x = data_augmentation(inputs)
        x = tf.keras.layers.Rescaling(1./255)(x)
        x = base_model(x, training=False)
        x = tf.keras.layers.Dense(128, activation='relu')(x)
        x = tf.keras.layers.Dropout(0.5)(x)
        outputs = tf.keras.layers.Dense(self.num_classes, activation='softmax')(x)

        self.model = tf.keras.Model(inputs, outputs)
        return self.model, base_model
    
    def train_model(self, epochs=10):
        """Train the model with initial training and fine-tuning"""
        model, base_model = self.create_model()
        
        model.compile(
            optimizer=tf.keras.optimizers.Adam(),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )

        early_stopping = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)
        reduce_lr = tf.keras.callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3, verbose=1)

        # Initial training
        history = model.fit(
            self.train_dataset,
            validation_data=self.val_dataset,
            epochs=epochs,
            callbacks=[early_stopping, reduce_lr]
        )

        # Fine-tuning
        base_model.trainable = True
        model.compile(
            optimizer=tf.keras.optimizers.Adam(1e-5),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )
        
        history_finetune = model.fit(
            self.train_dataset,
            validation_data=self.val_dataset,
            epochs=epochs,
            callbacks=[early_stopping, reduce_lr]
        )
        
        return model, history, history_finetune
    
    def evaluate_model(self, model):
        """Evaluate the model and generate metrics"""
        test_loss, test_acc = model.evaluate(self.test_dataset)
        print(f"Test accuracy: {test_acc:.2f}")
        
        # Predict on test set
        y_true = []
        y_pred = []

        for images, labels in self.test_dataset:
            preds = model.predict(images)
            y_true.extend(np.argmax(labels.numpy(), axis=1))
            y_pred.extend(np.argmax(preds, axis=1))

        # Confusion matrix
        cm = confusion_matrix(y_true, y_pred)
        disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=self.class_names)
        disp.plot(cmap='Blues')
        plt.title("Confusion Matrix")
        plt.show()

        # Classification report
        report = classification_report(y_true, y_pred, target_names=self.class_names, digits=4)
        accuracy = accuracy_score(y_true, y_pred)

        print("Classification Report:")
        print(report)
        print(f"Overall Accuracy: {accuracy:.4f}")
        
        return test_acc, report, accuracy
    
    def save_model(self, model):
        """Save the trained model"""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        model.save(self.model_path)
        print(f"Model saved to: {self.model_path}")
        
    def run_full_training(self, epochs=10):
        """Run the complete training pipeline"""
        print("Starting mango classification model training...")
        
        # Count images
        self.count_images_per_class()
        
        # Load datasets
        self.load_datasets()
        
        # Train model
        model, history, history_finetune = self.train_model(epochs)
        
        # Evaluate model
        test_acc, report, accuracy = self.evaluate_model(model)
        
        # Save model
        self.save_model(model)
        
        return model, test_acc, report