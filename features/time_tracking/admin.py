from django.contrib import admin

from .models import TimeEntry, WorkSession


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'project', 'task', 'start', 'end', 'source', 'inactive_minutes')
    list_filter = ('source', 'project')
    search_fields = ('user__username', 'comment')


admin.site.register(WorkSession)
