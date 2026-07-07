from django.db.models import Q

from features.accounts.models import UserProfile, is_management, user_role

from .models import Project


def visible_projects(user):
    if is_management(user):
        return Project.objects.all()

    if user_role(user) == UserProfile.Role.CLIENT:
        return Project.objects.filter(Q(client=user) | Q(projectassignment__user=user)).distinct()

    return Project.objects.filter(projectassignment__user=user).distinct()
