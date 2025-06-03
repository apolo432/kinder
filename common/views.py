# common/views.py
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import render
from django.views.generic import ListView
from django.utils.decorators import method_decorator
from django.db.models import Q
from django.contrib.auth import get_user_model
from .models import LogModel

User = get_user_model()


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin to require admin role"""

    def test_func(self):
        return self.request.user.is_admin or self.request.user.is_superuser


@method_decorator(login_required, name='dispatch')
class LogListView(AdminRequiredMixin, ListView):
    """View to display system logs - admin only"""
    model = LogModel
    template_name = 'common/log_list.html'
    context_object_name = 'logs'
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset()

        # Search functionality
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(action__icontains=search) |
                Q(object_name__icontains=search) |
                Q(user__username__icontains=search)
            )

        # Filter by user if provided
        user_id = self.request.GET.get('user')
        if user_id and user_id != '':
            queryset = queryset.filter(user_id=user_id)

        # Filter by action type
        action_type = self.request.GET.get('action_type')
        if action_type and action_type != '':
            queryset = queryset.filter(action_type=action_type)

        # Filter by model type
        model_type = self.request.GET.get('model_type')
        if model_type and model_type != '':
            queryset = queryset.filter(model_type=model_type)

        # Date filtering
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')

        if date_from:
            queryset = queryset.filter(timestamp__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__date__lte=date_to)

        return queryset.select_related('user')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['users'] = User.objects.all().order_by('username')
        context['action_types'] = LogModel.ACTION_CHOICES
        context['model_types'] = LogModel.MODEL_CHOICES

        # Preserve filters in pagination
        context['current_filters'] = {
            'search': self.request.GET.get('search', ''),
            'user': self.request.GET.get('user', ''),
            'action_type': self.request.GET.get('action_type', ''),
            'model_type': self.request.GET.get('model_type', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
        }

        # Statistics
        context['total_logs'] = self.get_queryset().count()

        return context


@login_required
def websocket_test(request):
    """Test page for WebSocket connections"""
    return render(request, 'websocket_test.html')