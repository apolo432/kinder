from django.urls import path
from .views import websocket_test, LogListView

urlpatterns = [
    path('websocket-test/', websocket_test, name='websocket-test'),
    path('logs/', LogListView.as_view(), name='log-list'),

]