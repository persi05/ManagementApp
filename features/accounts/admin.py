from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'bank_account', 'is_blocked')
    list_filter = ('role', 'is_blocked')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__email', 'bank_account')
