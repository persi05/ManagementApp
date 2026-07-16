from django.db.models import Q

from features.accounts.models import UserProfile, is_management, user_role
from features.projects.selectors import visible_projects

from .models import Task
from .services import visible_columns


def visible_tasks(user):
    projects = visible_projects(user)
    tasks = Task.objects.select_related('project', 'column', 'assignee').prefetch_related('assignees').filter(project__in=projects)

    if user_role(user) == UserProfile.Role.EMPLOYEE and not is_management(user):
        tasks = tasks.filter(Q(assignee=user) | Q(assignees=user) | Q(project__projectassignment__user=user)).distinct()

    if not is_management(user):
        visible_column_ids = []
        for project in projects:
            visible_column_ids.extend(visible_columns(user, project).values_list('id', flat=True))
        tasks = tasks.filter(column_id__in=visible_column_ids)

    return tasks
