# common/signals.py
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from threading import local
from .models import LogModel

# Thread-local storage to keep track of the current user
_user = local()


class CurrentUserMiddleware:
    """Middleware to store current user in thread-local storage"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _user.value = getattr(request, 'user', None)
        response = self.get_response(request)
        if hasattr(_user, 'value'):
            del _user.value
        return response


def get_current_user():
    """Get current user from thread-local storage"""
    return getattr(_user, 'value', None)


def log_detailed_action(action_type, model_type, instance, user=None, details=None):
    """Enhanced logging function with more details"""
    if user is None:
        user = get_current_user()

    if user and user.is_authenticated:
        LogModel.objects.create(
            user=user,
            action=f"{action_type.title()} {model_type}: {str(instance)}",
            action_type=action_type.upper(),
            model_type=model_type,
            object_id=instance.pk if hasattr(instance, 'pk') else None,
            object_name=str(instance),
            details=details
        )


# Enhanced ingredient signals
@receiver(post_save, sender='ingredients.Ingredient')
def log_ingredient_save_enhanced(sender, instance, created, **kwargs):
    action_type = 'CREATE' if created else 'UPDATE'
    details = {
        'current_quantity': instance.current_quantity,
        'threshold_quantity': instance.threshold_quantity,
        'unit_price': float(instance.unit_price),
        'is_below_threshold': instance.is_below_threshold
    }
    log_detailed_action(action_type, 'ingredient', instance, details=details)


@receiver(post_delete, sender='ingredients.Ingredient')
def log_ingredient_delete_enhanced(sender, instance, **kwargs):
    log_detailed_action('DELETE', 'ingredient', instance)


# Ingredient Delivery signals
@receiver(post_save, sender='ingredients.IngredientDelivery')
def log_ingredient_delivery(sender, instance, created, **kwargs):
    if created:
        details = {
            'quantity': instance.quantity,
            'delivery_date': instance.delivery_date.isoformat(),
            'notes': instance.notes
        }
        log_detailed_action('CREATE', 'ingredient_delivery', instance, details=details)


@receiver(post_delete, sender='ingredients.IngredientDelivery')
def log_ingredient_delivery_delete(sender, instance, **kwargs):
    log_detailed_action('DELETE', 'ingredient_delivery', instance)


# Ingredient Usage signals
@receiver(post_save, sender='ingredients.IngredientUsage')
def log_ingredient_usage(sender, instance, created, **kwargs):
    if created:
        details = {
            'quantity': instance.quantity,
            'meal_id': instance.meal.id if instance.meal else None,
            'meal_name': instance.meal.meal.name if instance.meal else None
        }
        log_detailed_action('USE_QUANTITY', 'ingredient_usage', instance, details=details)


# Enhanced meal signals
@receiver(post_save, sender='meals.Meal')
def log_meal_save_enhanced(sender, instance, created, **kwargs):
    action_type = 'CREATE' if created else 'UPDATE'
    details = {
        'description': instance.description,
        'total_ingredients': instance.ingredients.count(),
        'max_portions': instance.max_possible_portions()
    }
    log_detailed_action(action_type, 'meal', instance, details=details)


@receiver(post_delete, sender='meals.Meal')
def log_meal_delete(sender, instance, **kwargs):
    log_detailed_action('DELETE', 'meal', instance)


# Meal Ingredient signals
@receiver(post_save, sender='meals.MealIngredient')
def log_meal_ingredient_save(sender, instance, created, **kwargs):
    action_type = 'CREATE' if created else 'UPDATE'
    details = {
        'ingredient_name': instance.ingredient.name,
        'quantity': instance.quantity,
        'meal_name': instance.meal.name
    }
    log_detailed_action(action_type, 'meal_ingredient', instance, details=details)


@receiver(post_delete, sender='meals.MealIngredient')
def log_meal_ingredient_delete(sender, instance, **kwargs):
    details = {
        'ingredient_name': instance.ingredient.name,
        'quantity': instance.quantity,
        'meal_name': instance.meal.name
    }
    log_detailed_action('DELETE', 'meal_ingredient', instance, details=details)


# Meal Serving signals
@receiver(post_save, sender='meals.MealServing')
def log_meal_serving(sender, instance, created, **kwargs):
    if created:
        details = {
            'servings': instance.servings,
            'meal_name': instance.meal.name,
            'serving_date': instance.serving_date.isoformat(),
            'notes': instance.notes
        }
        log_detailed_action('SERVE', 'meal_serving', instance, details=details)


@receiver(post_delete, sender='meals.MealServing')
def log_meal_serving_delete(sender, instance, **kwargs):
    log_detailed_action('DELETE', 'meal_serving', instance)