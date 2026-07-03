from django.db.models import Q

from .models import Project, Task, UserProfile, is_management, user_role


def visible_projects(user):
    if is_management(user):
        return Project.objects.all()

    if user_role(user) == UserProfile.Role.CLIENT:
        return Project.objects.filter(Q(client=user) | Q(projectassignment__user=user)).distinct()

    return Project.objects.filter(projectassignment__user=user).distinct()


def visible_tasks(user):
    projects = visible_projects(user)
    tasks = Task.objects.select_related('project', 'column', 'assignee').filter(project__in=projects)

    if user_role(user) == UserProfile.Role.EMPLOYEE and not is_management(user):
        tasks = tasks.filter(Q(assignee=user) | Q(project__projectassignment__user=user)).distinct()

    return tasks
