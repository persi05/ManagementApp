from django.contrib import admin

from .models import (
    Attachment,
    BoardColumn,
    ChecklistItem,
    Comment,
    HourlyRate,
    Notification,
    Project,
    ProjectAssignment,
    Task,
    TaskWorklog,
    TimeEntry,
    UserProfile,
    WorkSession,
)


class ProjectAssignmentInline(admin.TabularInline):
    model = ProjectAssignment
    extra = 1


class BoardColumnInline(admin.TabularInline):
    model = BoardColumn
    extra = 0


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'bank_account', 'is_blocked')
    list_filter = ('role', 'is_blocked')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__email', 'bank_account')


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'client', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'description')
    inlines = [ProjectAssignmentInline, BoardColumnInline]


@admin.register(BoardColumn)
class BoardColumnAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'position')
    list_filter = ('project',)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'column', 'assignee', 'priority', 'due_date')
    list_filter = ('project', 'priority', 'column')
    search_fields = ('title', 'description', 'labels')


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'project', 'task', 'start', 'end', 'source', 'inactive_minutes')
    list_filter = ('source', 'project')
    search_fields = ('user__username', 'comment')


@admin.register(TaskWorklog)
class TaskWorklogAdmin(admin.ModelAdmin):
    list_display = ('task', 'user', 'hours', 'date', 'visible_to_client')
    list_filter = ('visible_to_client', 'date')


@admin.register(HourlyRate)
class HourlyRateAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'currency', 'valid_from', 'valid_to')
    list_filter = ('currency',)


admin.site.register(ChecklistItem)
admin.site.register(WorkSession)
admin.site.register(Comment)
admin.site.register(Attachment)
admin.site.register(Notification)
