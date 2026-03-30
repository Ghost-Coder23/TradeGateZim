
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'phone', 'country', 'email_verified', 'is_staff']
    list_filter = ['country', 'email_verified', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone']
    fieldsets = UserAdmin.fieldsets + (
        ('TradeGate Profile', {'fields': ('phone', 'country', 'email_verified')}),
    )
