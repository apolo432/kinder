from django.urls import path
from .views import (
    ReportListView, ReportDetailView, dashboard, generate_report,
    ingredient_usage_chart_data, meal_serving_chart_data, discrepancy_chart_data
)


urlpatterns = [
    path('', ReportListView.as_view(), name='report-list'),
    path('<int:pk>/', ReportDetailView.as_view(), name='report-detail'),
    path('dashboard/', dashboard, name='dashboard'),
    path('generate/', generate_report, name='generate-report'),
    path('api/ingredient-usage-data/', ingredient_usage_chart_data, name='ingredient-usage-data'),
    path('api/meal-serving-data/', meal_serving_chart_data, name='meal-serving-data'),
    path('api/discrepancy-data/', discrepancy_chart_data, name='discrepancy-data'),
]