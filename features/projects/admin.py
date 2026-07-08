from django.contrib import admin

from features.tasks.models import BoardColumn

from .models import Project, ProjectAssignment, ProjectLabelRate


class ProjectAssignmentInline(admin.TabularInline):
    model = ProjectAssignment
    extra = 1


class BoardColumnInline(admin.TabularInline):
    model = BoardColumn
    extra = 0


class ProjectLabelRateInline(admin.TabularInline):
    model = ProjectLabelRate
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'client', 'status', 'client_hourly_rate', 'client_rate_currency', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'description')
    inlines = [ProjectAssignmentInline, ProjectLabelRateInline, BoardColumnInline]
