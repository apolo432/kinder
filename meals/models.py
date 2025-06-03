from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError


class Meal(models.Model):
    """
    Model to store meal information and recipes
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   related_name='created_meals')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_ingredients(self):
        """Return all ingredients for this meal"""
        return self.ingredients.all()

    def get_total_ingredients_weight(self):
        """Calculate the total weight of all ingredients in this meal"""
        return sum(mi.quantity for mi in self.ingredients.all())

    def can_be_served(self):
        """Check if all ingredients are available in sufficient quantities"""
        for meal_ingredient in self.ingredients.all():
            if meal_ingredient.ingredient.current_quantity < meal_ingredient.quantity:
                return False, f"Insufficient {meal_ingredient.ingredient.name}"
        return True, "All ingredients available"

    def max_possible_portions(self):
        """Calculate the maximum number of portions that can be made based on current inventory"""
        portions = []

        for meal_ingredient in self.ingredients.all():
            if meal_ingredient.quantity <= 0:
                continue

            # Calculate how many portions we can make with this ingredient
            possible_portions = meal_ingredient.ingredient.current_quantity // meal_ingredient.quantity
            portions.append(possible_portions)

        # The maximum possible portions is limited by the ingredient with the least available portions
        if not portions:
            return 0

        return min(portions)

    def serve(self, user, servings=1):
        """
        Serve this meal by deducting ingredients from inventory
        Returns a MealServing object if successful
        """
        # First check if we can serve this meal
        can_serve, message = self.can_be_served()
        if not can_serve:
            raise ValidationError(message)

        # Check if servings is a positive integer
        if not isinstance(servings, int) or servings <= 0:
            raise ValidationError("Servings must be a positive integer")

        # Create a serving record
        meal_serving = MealServing.objects.create(
            meal=self,
            served_by=user,
            servings=servings
        )

        # Reduce ingredients from inventory
        for meal_ingredient in self.ingredients.all():
            quantity_to_use = meal_ingredient.quantity * servings
            meal_ingredient.ingredient.reduce_quantity(
                quantity=quantity_to_use,
                user=user,
                meal=meal_serving
            )

        return meal_serving


class MealIngredient(models.Model):
    """
    Model to define the ingredients and quantities required for a meal
    """
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name='ingredients')
    ingredient = models.ForeignKey('ingredients.Ingredient', on_delete=models.CASCADE, related_name='used_in_meals')
    quantity = models.PositiveIntegerField(help_text="Quantity required per portion in grams")

    class Meta:
        ordering = ['ingredient__name']
        unique_together = ['meal', 'ingredient']

    def __str__(self):
        return f"{self.ingredient.name} ({self.quantity}g) for {self.meal.name}"

    def clean(self):
        """Validate that quantity is positive and reasonable"""
        if self.quantity <= 0:
            raise ValidationError("Quantity must be positive")

        if self.quantity > 5000:  # Arbitrary upper limit, adjust as needed
            raise ValidationError("Quantity seems unusually high. Please double-check.")


class MealServing(models.Model):
    """
    Model to track when meals are served
    """
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name='servings')
    serving_date = models.DateTimeField(default=timezone.now)
    served_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                  related_name='served_meals')
    servings = models.PositiveIntegerField(default=1, help_text="Number of portions served")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-serving_date']

    def __str__(self):
        return f"{self.meal.name} served on {self.serving_date.strftime('%Y-%m-%d %H:%M')}"

    def get_total_ingredients_used(self):
        """Calculate the total ingredients used for this serving"""
        result = {}
        for meal_ingredient in self.meal.ingredients.all():
            total_quantity = meal_ingredient.quantity * self.servings
            result[meal_ingredient.ingredient.name] = total_quantity
        return result