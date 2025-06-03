from django.db import models
from django.utils import timezone
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


class Ingredient(models.Model):
    """
    Model to store ingredient information
    """
    name = models.CharField(max_length=100, unique=True)
    current_quantity = models.PositiveIntegerField(default=0, help_text="Current quantity in grams")
    threshold_quantity = models.PositiveIntegerField(default=1000, help_text="Minimum threshold for warning in grams")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                     help_text="Price per kg in local currency")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.current_quantity}g)"

    @property
    def is_below_threshold(self):
        """Check if the ingredient quantity is below the threshold"""
        return self.current_quantity < self.threshold_quantity

    def add_quantity(self, quantity, user):
        """Add quantity to the ingredient and create a delivery record"""
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        self.current_quantity += quantity
        self.save()

        # Create a delivery record
        IngredientDelivery.objects.create(
            ingredient=self,
            quantity=quantity,
            created_by=user
        )

        # Send WebSocket notification if not in testing mode
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "inventory_updates",
                    {
                        'type': 'inventory_update',
                        'ingredient_id': self.id,
                        'ingredient_name': self.name,
                        'current_quantity': self.current_quantity,
                        'threshold_quantity': self.threshold_quantity,
                        'is_below_threshold': self.is_below_threshold
                    }
                )

                # Also send low ingredient alert if needed
                if self.is_below_threshold:
                    async_to_sync(channel_layer.group_send)(
                        "inventory_updates",
                        {
                            'type': 'low_ingredient_alert',
                            'ingredient_id': self.id,
                            'ingredient_name': self.name,
                            'current_quantity': self.current_quantity,
                            'threshold_quantity': self.threshold_quantity
                        }
                    )
        except:
            # If WebSocket channel layer is not available, just continue
            pass

        return self.current_quantity

    def reduce_quantity(self, quantity, user, meal=None):
        """Reduce quantity from the ingredient and create a usage record"""
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if quantity > self.current_quantity:
            raise ValueError(f"Insufficient quantity of {self.name}")

        self.current_quantity -= quantity
        self.save()

        # Create a usage record
        IngredientUsage.objects.create(
            ingredient=self,
            quantity=quantity,
            created_by=user,
            meal=meal
        )

        # Send WebSocket notification if not in testing mode
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "inventory_updates",
                    {
                        'type': 'inventory_update',
                        'ingredient_id': self.id,
                        'ingredient_name': self.name,
                        'current_quantity': self.current_quantity,
                        'threshold_quantity': self.threshold_quantity,
                        'is_below_threshold': self.is_below_threshold
                    }
                )

                # Also send low ingredient alert if needed
                if self.is_below_threshold:
                    async_to_sync(channel_layer.group_send)(
                        "inventory_updates",
                        {
                            'type': 'low_ingredient_alert',
                            'ingredient_id': self.id,
                            'ingredient_name': self.name,
                            'current_quantity': self.current_quantity,
                            'threshold_quantity': self.threshold_quantity
                        }
                    )
        except:
            # If WebSocket channel layer is not available, just continue
            pass

        return self.current_quantity


class IngredientDelivery(models.Model):
    """
    Model to track ingredient deliveries
    """
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name='deliveries')
    quantity = models.PositiveIntegerField(help_text="Quantity delivered in grams")
    delivery_date = models.DateField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-delivery_date']
        verbose_name_plural = 'Ingredient deliveries'

    def __str__(self):
        return f"{self.ingredient.name} delivery: {self.quantity}g on {self.delivery_date}"


class IngredientUsage(models.Model):
    """
    Model to track ingredient usage
    """
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name='usages')
    quantity = models.PositiveIntegerField(help_text="Quantity used in grams")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    meal = models.ForeignKey('meals.MealServing', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ingredient.name} used: {self.quantity}g on {self.created_at.date()}"