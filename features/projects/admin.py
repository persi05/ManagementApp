from django.contrib import admin

from features.tasks.models import BoardColumn

from .models import Project, ProjectAssignment


class ProjectAssignmentInline(admin.TabularInline):
    model = ProjectAssignment
    extra = 1


class BoardColumnInline(admin.TabularInline):
    model = BoardColumn
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'client', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'description')
    inlines = [ProjectAssignmentInline, BoardColumnInline]
