import calendar
from datetime import datetime, timedelta
from django.db.models import Sum, Count, F, Q, Case, When, IntegerField
from django.utils import timezone
from django.conf import settings
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import MonthlyReport, ReportIngredientUsage, ReportMealServing
from meals.models import MealServing, Meal
from ingredients.models import IngredientDelivery, IngredientUsage, Ingredient


@shared_task
def generate_monthly_report(year, month, user_id=None):
    """
    Generate a monthly report for the specified year and month
    If a report already exists for this period, it will be updated
    """
    # Define the period boundaries
    _, last_day = calendar.monthrange(year, month)
    start_date = datetime(year, month, 1, 0, 0, 0)
    end_date = datetime(year, month, last_day, 23, 59, 59)

    # Get or create the report
    report, created = MonthlyReport.objects.get_or_create(
        year=year,
        month=month,
        defaults={'generated_by_id': user_id}
    )

    # If updating an existing report, clean old data
    if not created:
        report.ingredient_usages.all().delete()
        report.meal_servings.all().delete()

    # Get all meal servings for the month
    meal_servings = MealServing.objects.filter(
        serving_date__gte=start_date,
        serving_date__lte=end_date
    )

    # Get ingredient deliveries for the month
    ingredient_deliveries = IngredientDelivery.objects.filter(
        delivery_date__gte=start_date.date(),
        delivery_date__lte=end_date.date()
    )

    # Get ingredient usages for the month
    ingredient_usages = IngredientUsage.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    # Calculate summary statistics
    total_meals_served = meal_servings.values('meal').distinct().count()
    total_servings = meal_servings.aggregate(total=Sum('servings'))['total'] or 0

    # Calculate potential servings based on historical usage and deliveries
    total_ingredients_used = ingredient_usages.aggregate(total=Sum('quantity'))['total'] or 0
    total_ingredients_delivered = ingredient_deliveries.aggregate(total=Sum('quantity'))['total'] or 0

    # Estimate potential servings using a simple algorithm:
    # 1. Calculate average ingredients per serving
    if total_servings > 0:
        avg_ingredients_per_serving = total_ingredients_used / total_servings
        # 2. Estimate potential servings based on delivered ingredients
        total_potential_servings = int(total_ingredients_delivered / avg_ingredients_per_serving)
    else:
        total_potential_servings = 0

    # Calculate discrepancy rate
    if total_potential_servings > 0:
        discrepancy_rate = ((total_potential_servings - total_servings) / total_potential_servings) * 100
    else:
        discrepancy_rate = 0

    # Flag high discrepancy
    high_discrepancy = discrepancy_rate > 15  # Flag if discrepancy rate exceeds 15%

    # Update the report
    report.total_meals_served = total_meals_served
    report.total_servings = total_servings
    report.total_potential_servings = total_potential_servings
    report.discrepancy_rate = round(discrepancy_rate, 2)
    report.total_ingredients_used = total_ingredients_used
    report.total_ingredients_delivered = total_ingredients_delivered
    report.high_discrepancy = high_discrepancy
    report.save()

    # Generate ingredient usage details
    ingredients = Ingredient.objects.all()
    for ingredient in ingredients:
        # Get usage for this ingredient in the period
        used = ingredient_usages.filter(
            ingredient=ingredient
        ).aggregate(total=Sum('quantity'))['total'] or 0

        # Get deliveries for this ingredient in the period
        delivered = ingredient_deliveries.filter(
            ingredient=ingredient
        ).aggregate(total=Sum('quantity'))['total'] or 0

        # Only add to report if there was activity
        if used > 0 or delivered > 0:
            ReportIngredientUsage.objects.create(
                report=report,
                ingredient_name=ingredient.name,
                quantity_used=used,
                quantity_delivered=delivered,
                discrepancy=delivered - used
            )

    # Generate meal serving details
    meals = Meal.objects.all()
    for meal in meals:
        # Get servings for this meal in the period
        servings = meal_servings.filter(meal=meal)
        servings_count = servings.aggregate(total=Sum('servings'))['total'] or 0

        # Only add to report if there were servings
        if servings_count > 0:
            # Estimate ingredients used
            meal_ingredients = meal.ingredients.all()
            total_ingredients = sum(mi.quantity * servings_count for mi in meal_ingredients)

            ReportMealServing.objects.create(
                report=report,
                meal_name=meal.name,
                servings_count=servings_count,
                total_ingredients_used=total_ingredients
            )

    return report


@shared_task
def auto_generate_monthly_reports():
    """
    Automatically generate reports for the previous month
    This task can be scheduled to run on the 1st of each month
    """
    # Calculate previous month
    today = timezone.now()
    if today.month == 1:
        year = today.year - 1
        month = 12
    else:
        year = today.year
        month = today.month - 1

    # Generate the report
    return generate_monthly_report(year, month)


@shared_task
def check_low_ingredients(ingredient_id=None):
    """
    Check for ingredients below threshold and send notifications
    This task can be scheduled to run daily or triggered by signals

    Args:
        ingredient_id: Optional ID of a specific ingredient to check.
                      If None, checks all ingredients.
    """
    if ingredient_id:
        # Check only the specified ingredient
        try:
            ingredient = Ingredient.objects.get(id=ingredient_id)
            low_ingredients = [ingredient] if ingredient.is_below_threshold else []
        except Ingredient.DoesNotExist:
            return "Ingredient not found"
    else:
        # Check all ingredients
        low_ingredients = list(Ingredient.objects.filter(current_quantity__lt=F('threshold_quantity')))

    # Send email notifications (in a real app)
    if low_ingredients:
        # Example email notification code (commented out)
        # from django.core.mail import send_mail
        # ingredients_list = "\n".join([f"- {i.name}: {i.current_quantity}g (threshold: {i.threshold_quantity}g)" for i in low_ingredients])
        # send_mail(
        #     'Low Ingredient Alert',
        #     f'The following ingredients are below threshold:\n{ingredients_list}',
        #     'from@example.com',
        #     ['to@example.com'],
        #     fail_silently=False,
        # )
        pass

    # Send WebSocket alerts for low ingredients
    try:
        channel_layer = get_channel_layer()
        if channel_layer and low_ingredients:
            for ingredient in low_ingredients:
                async_to_sync(channel_layer.group_send)(
                    "inventory_updates",
                    {
                        'type': 'low_ingredient_alert',
                        'ingredient_id': ingredient.id,
                        'ingredient_name': ingredient.name,
                        'current_quantity': ingredient.current_quantity,
                        'threshold_quantity': ingredient.threshold_quantity
                    }
                )
    except:
        # If WebSocket channel layer is not available, just continue
        pass

    return f"Checked {len(low_ingredients)} low ingredients"


@shared_task
def recalculate_portion_estimates():
    """
    Recalculate the estimated portions for all meals
    This task can be scheduled to run periodically
    """
    meals = Meal.objects.all()
    results = {}

    for meal in meals:
        max_portions = meal.max_possible_portions()
        results[meal.name] = max_portions

        # Send WebSocket updates for portion estimates
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "meal_servings",
                    {
                        'type': 'portions_update',
                        'meal_id': meal.id,
                        'meal_name': meal.name,
                        'max_portions': max_portions
                    }
                )
        except:
            # If WebSocket channel layer is not available, just continue
            pass

    return results