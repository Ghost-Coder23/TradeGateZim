from django.urls import path
from . import views

urlpatterns = [
    path('deposit/', views.deposit_view, name='deposit'),
    path('withdraw/', views.withdrawal_view, name='withdrawal'),
    path('transactions/', views.transaction_list_view, name='transaction_list'),
    path('transactions/<uuid:pk>/', views.transaction_detail_view, name='transaction_detail'),
    path('transactions/<uuid:pk>/simulate/', views.simulate_payment_view, name='simulate_payment'),
    path('transactions/<uuid:pk>/cancel/', views.cancel_transaction_view, name='cancel_transaction'),
    path('rates/', views.rates_view, name='rates'),
]
