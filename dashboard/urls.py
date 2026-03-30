from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('admin-panel/', views.admin_dashboard_view, name='admin_panel'),
    path('admin-panel/fees/update/', views.admin_fee_settings_update_view, name='admin_fee_settings_update'),
    path('admin-panel/transactions/<uuid:pk>/action/', views.admin_transaction_action_view, name='admin_transaction_action'),
]
