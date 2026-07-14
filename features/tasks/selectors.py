from django.db.models import Q

from features.accounts.models import UserProfile, is_management, user_role
from features.projects.selectors import visible_projects

from .models import Task


def visible_tasks(user):
    projects = visible_projects(user)
    tasks = Task.objects.select_related('project', 'column', 'assignee').prefetch_related('assignees').filter(project__in=projects)

    if user_role(user) == UserProfile.Role.EMPLOYEE and not is_management(user):
        tasks = tasks.filter(Q(assignee=user) | Q(assignees=user) | Q(project__projectassignment__user=user)).distinct()

    return tasks
