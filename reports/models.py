from django.db import models
from django.utils import timezone
from django.conf import settings


class MonthlyReport(models.Model):
    """
    Model to store generated monthly reports
    """
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    # Summary statistics
    total_meals_served = models.PositiveIntegerField(default=0)
    total_servings = models.PositiveIntegerField(default=0)
    total_potential_servings = models.PositiveIntegerField(default=0)
    discrepancy_rate = models.FloatField(default=0.0, help_text="Discrepancy rate in percentage")

    # Ingredient statistics
    total_ingredients_used = models.PositiveIntegerField(default=0, help_text="Total ingredients used in grams")
    total_ingredients_delivered = models.PositiveIntegerField(default=0,
                                                              help_text="Total ingredients delivered in grams")

    # Flags
    high_discrepancy = models.BooleanField(default=False, help_text="Flag if discrepancy rate exceeds threshold")

    class Meta:
        ordering = ['-year', '-month']
        unique_together = ['year', 'month']

    def __str__(self):
        return f"Report for {self.year}-{self.month:02d}"

    @property
    def month_name(self):
        """Return the month name"""
        month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                       'July', 'August', 'September', 'October', 'November', 'December']
        return month_names[self.month - 1]

    @property
    def period_label(self):
        """Return a formatted period label"""
        return f"{self.month_name} {self.year}"

    @classmethod
    def get_or_generate_report(cls, year, month, user=None):
        """Get existing report or generate a new one"""
        try:
            return cls.objects.get(year=year, month=month)
        except cls.DoesNotExist:
            from .tasks import generate_monthly_report
            return generate_monthly_report(year, month, user)


class ReportIngredientUsage(models.Model):
    """
    Model to store ingredient usage details for monthly reports
    """
    report = models.ForeignKey(MonthlyReport, on_delete=models.CASCADE, related_name='ingredient_usages')
    ingredient_name = models.CharField(max_length=100)

    # Quantities
    quantity_used = models.PositiveIntegerField(default=0, help_text="Quantity used in grams")
    quantity_delivered = models.PositiveIntegerField(default=0, help_text="Quantity delivered in grams")
    discrepancy = models.IntegerField(default=0, help_text="Discrepancy in grams")

    class Meta:
        ordering = ['-quantity_used']

    def __str__(self):
        return f"{self.ingredient_name} usage in {self.report}"


class ReportMealServing(models.Model):
    """
    Model to store meal serving details for monthly reports
    """
    report = models.ForeignKey(MonthlyReport, on_delete=models.CASCADE, related_name='meal_servings')
    meal_name = models.CharField(max_length=100)

    # Statistics
    servings_count = models.PositiveIntegerField(default=0)
    total_ingredients_used = models.PositiveIntegerField(default=0, help_text="Total ingredients used in grams")

    class Meta:
        ordering = ['-servings_count']

    def __str__(self):
        return f"{self.meal_name} servings in {self.report}"