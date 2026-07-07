from django.contrib import admin

from .models import Attachment, BoardColumn, ChecklistItem, Comment, Notification, Task, TaskEditNote, TaskWorklog


@admin.register(BoardColumn)
class BoardColumnAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'position')
    list_filter = ('project',)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'column', 'assignee', 'priority', 'due_date')
    list_filter = ('project', 'priority', 'column')
    search_fields = ('title', 'description')


@admin.register(TaskWorklog)
class TaskWorklogAdmin(admin.ModelAdmin):
    list_display = ('task', 'user', 'hours', 'date', 'visible_to_client')
    list_filter = ('visible_to_client', 'date')


admin.site.register(ChecklistItem)
admin.site.register(Comment)
admin.site.register(Attachment)
admin.site.register(Notification)
admin.site.register(TaskEditNote)
