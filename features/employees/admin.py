from django.contrib import admin

from .models import HourlyRate


@admin.register(HourlyRate)
class HourlyRateAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'currency', 'valid_from', 'valid_to')
    list_filter = ('currency',)
