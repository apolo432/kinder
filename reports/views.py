from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from django.utils.decorators import method_decorator
import calendar
import datetime

from .models import MonthlyReport, ReportIngredientUsage, ReportMealServing
from .tasks import generate_monthly_report
from meals.models import MealServing
from ingredients.models import IngredientUsage, IngredientDelivery, Ingredient
from common.permissions import IsAdmin, IsManager


class ReportAccessMixin(UserPassesTestMixin):
    """Mixin to require manager or admin role for reports"""

    def test_func(self):
        return self.request.user.is_admin or self.request.user.is_manager


@method_decorator(login_required, name='dispatch')
class ReportListView(ReportAccessMixin, ListView):
    """List all monthly reports"""
    model = MonthlyReport
    template_name = 'reports/report_list.html'
    context_object_name = 'reports'


@method_decorator(login_required, name='dispatch')
class ReportDetailView(ReportAccessMixin, DetailView):
    """View monthly report details"""
    model = MonthlyReport
    template_name = 'reports/report_detail.html'
    context_object_name = 'report'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report = self.get_object()

        # Add top ingredients by usage
        context['top_ingredients'] = report.ingredient_usages.order_by('-quantity_used')[:10]

        # Add top meals by servings
        context['top_meals'] = report.meal_servings.order_by('-servings_count')[:10]

        # Add ingredients with high discrepancy (waste or misuse)
        context['high_discrepancy_ingredients'] = report.ingredient_usages.filter(
            discrepancy__lt=0  # Negative discrepancy means more used than delivered
        ).order_by('discrepancy')[:10]

        return context


@login_required
def dashboard(request):
    """Main dashboard view with summary statistics and charts"""
    if not (request.user.is_admin or request.user.is_manager):
        # Redirect cooks to the meals list
        return redirect('meal-list')

    # Get current month
    today = timezone.now()
    year = today.year
    month = today.month

    # Try to get current month's report
    try:
        current_report = MonthlyReport.objects.get(year=year, month=month)
    except MonthlyReport.DoesNotExist:
        current_report = None

    # Get recent servings
    recent_servings = MealServing.objects.select_related('meal', 'served_by').order_by('-serving_date')[:10]

    # Get ingredients below threshold
    ingredients = Ingredient.objects.all()
    low_ingredients = list(filter(
        lambda i: i.is_below_threshold,
        sorted(list(ingredients), key=lambda x: (x.current_quantity / x.threshold_quantity))
    ))[:5]

    # Calculate today's serving stats
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_servings = MealServing.objects.filter(serving_date__gte=today_start)
    today_servings_count = today_servings.aggregate(total=Sum('servings'))['total'] or 0
    today_meals_count = today_servings.values('meal').distinct().count()

    # Calculate this week's serving stats
    week_start = today - datetime.timedelta(days=today.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_servings = MealServing.objects.filter(serving_date__gte=week_start)
    week_servings_count = week_servings.aggregate(total=Sum('servings'))['total'] or 0

    context = {
        'current_report': current_report,
        'recent_servings': recent_servings,
        'low_ingredients': low_ingredients,
        'today_servings_count': today_servings_count,
        'today_meals_count': today_meals_count,
        'week_servings_count': week_servings_count,
    }

    return render(request, 'reports/dashboard.html', context)


@login_required
def generate_report(request):
    """View to manually trigger report generation"""
    if not (request.user.is_admin or request.user.is_manager):
        messages.error(request, "You don't have permission to generate reports")
        return redirect('dashboard')

    if request.method == 'POST':
        year = int(request.POST.get('year'))
        month = int(request.POST.get('month'))

        # Generate the report (synchronously for simplicity)
        report = generate_monthly_report(year, month, request.user.id)

        messages.success(request, f"Report for {report.period_label} generated successfully")
        return redirect('report-detail', pk=report.id)

    # Prepare available years and months
    current_year = timezone.now().year
    years = range(current_year - 2, current_year + 1)
    months = [(i, calendar.month_name[i]) for i in range(1, 13)]

    return render(request, 'reports/generate_report.html', {
        'years': years,
        'months': months
    })


@login_required
def ingredient_usage_chart_data(request):
    """API endpoint to get ingredient usage data for charts"""
    if not (request.user.is_admin or request.user.is_manager):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Get parameters
    ingredient_id = request.GET.get('ingredient')
    period = request.GET.get('period', 'month')  # month, quarter, year

    # Define the time range
    today = timezone.now()

    if period == 'month':
        # Last 30 days
        start_date = today - datetime.timedelta(days=30)
        date_format = '%Y-%m-%d'
        group_by = 'date'
    elif period == 'quarter':
        # Last 90 days
        start_date = today - datetime.timedelta(days=90)
        date_format = '%Y-%W'  # Year-Week
        group_by = 'week'
    else:  # year
        # Last 365 days
        start_date = today - datetime.timedelta(days=365)
        date_format = '%Y-%m'  # Year-Month
        group_by = 'month'

    # Base queries
    usage_query = IngredientUsage.objects.filter(created_at__gte=start_date)
    delivery_query = IngredientDelivery.objects.filter(delivery_date__gte=start_date.date())

    # Filter by ingredient if provided
    if ingredient_id:
        usage_query = usage_query.filter(ingredient_id=ingredient_id)
        delivery_query = delivery_query.filter(ingredient_id=ingredient_id)

    # Process usage data
    usage_data = {}
    for usage in usage_query:
        date_key = usage.created_at.strftime(date_format)
        usage_data[date_key] = usage_data.get(date_key, 0) + usage.quantity

    # Process delivery data
    delivery_data = {}
    for delivery in delivery_query:
        date_key = delivery.delivery_date.strftime(date_format)
        delivery_data[date_key] = delivery_data.get(date_key, 0) + delivery.quantity

    # Combine all dates
    all_dates = set(list(usage_data.keys()) + list(delivery_data.keys()))
    sorted_dates = sorted(all_dates)

    # Prepare chart data
    chart_data = []
    for date_key in sorted_dates:
        chart_data.append({
            'period': date_key,
            'usage': usage_data.get(date_key, 0),
            'delivery': delivery_data.get(date_key, 0)
        })

    return JsonResponse(chart_data, safe=False)


@login_required
def meal_serving_chart_data(request):
    """API endpoint to get meal serving data for charts"""
    if not (request.user.is_admin or request.user.is_manager):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Get parameters
    meal_id = request.GET.get('meal')
    period = request.GET.get('period', 'month')  # month, quarter, year

    # Define the time range
    today = timezone.now()

    if period == 'month':
        # Last 30 days
        start_date = today - datetime.timedelta(days=30)
        date_format = '%Y-%m-%d'
    elif period == 'quarter':
        # Last 90 days
        start_date = today - datetime.timedelta(days=90)
        date_format = '%Y-%W'  # Year-Week
    else:  # year
        # Last 365 days
        start_date = today - datetime.timedelta(days=365)
        date_format = '%Y-%m'  # Year-Month

    # Base query
    serving_query = MealServing.objects.filter(serving_date__gte=start_date)

    # Filter by meal if provided
    if meal_id:
        serving_query = serving_query.filter(meal_id=meal_id)

    # Process serving data
    serving_data = {}
    for serving in serving_query:
        date_key = serving.serving_date.strftime(date_format)
        serving_data[date_key] = serving_data.get(date_key, 0) + serving.servings

    # Prepare chart data
    chart_data = []
    for date_key in sorted(serving_data.keys()):
        chart_data.append({
            'period': date_key,
            'servings': serving_data[date_key]
        })

    return JsonResponse(chart_data, safe=False)


@login_required
def discrepancy_chart_data(request):
    """API endpoint to get discrepancy rate data for charts"""
    if not (request.user.is_admin or request.user.is_manager):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Get all reports, ordered by date
    reports = MonthlyReport.objects.all().order_by('year', 'month')

    chart_data = []
    for report in reports:
        chart_data.append({
            'period': f"{report.year}-{report.month:02d}",
            'period_label': report.period_label,
            'discrepancy_rate': report.discrepancy_rate,
            'high_discrepancy': report.high_discrepancy,
            'total_servings': report.total_servings,
            'total_potential_servings': report.total_potential_servings
        })

    return JsonResponse(chart_data, safe=False)