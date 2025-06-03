from django.db import models
from django.conf import settings


class LogModel(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('SERVE', 'Serve'),
        ('ADD_QUANTITY', 'Add Quantity'),
        ('USE_QUANTITY', 'Use Quantity'),
    ]

    MODEL_CHOICES = [
        ('ingredient', 'Ingredient'),
        ('meal', 'Meal'),
        ('meal_ingredient', 'Meal Ingredient'),
        ('meal_serving', 'Meal Serving'),
        ('ingredient_delivery', 'Ingredient Delivery'),
        ('ingredient_usage', 'Ingredient Usage'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=255)
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES, null=True, blank=True)
    model_type = models.CharField(max_length=30, choices=MODEL_CHOICES, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    object_name = models.CharField(max_length=255, null=True, blank=True)
    details = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username} - {self.action} at {self.timestamp}"