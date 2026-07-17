from django.contrib import admin

from .models import EmployeeCharge, HourlyRate


@admin.register(HourlyRate)
class HourlyRateAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'currency', 'valid_from', 'valid_to')
    list_filter = ('currency',)


@admin.register(EmployeeCharge)
class EmployeeChargeAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'amount', 'starts_at', 'created_by')
    search_fields = ('name', 'user__username', 'user__first_name', 'user__last_name')
