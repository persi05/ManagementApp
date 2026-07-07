from features.accounts.models import UserProfile, is_management, user_role
from features.projects.models import ProjectAssignment

from .models import BoardColumn


DEFAULT_BOARD_COLUMNS = ['Do zrobienia', 'W trakcie', 'Review', 'Zakonczone']


def ensure_default_columns(project):
    for position, name in enumerate(DEFAULT_BOARD_COLUMNS):
        BoardColumn.objects.get_or_create(
            project=project,
            name=name,
            defaults={'position': position},
        )


def project_role_for(user, project):
    if is_management(user):
        return UserProfile.Role.MANAGEMENT
    assignment = ProjectAssignment.objects.filter(project=project, user=user).only('project_role').first()
    if assignment:
        return assignment.project_role
    return user_role(user)


def task_move_limit(user, project):
    role = project_role_for(user, project)
    if role == UserProfile.Role.CLIENT:
        return None
    if role == ProjectAssignment.ProjectRole.LEAD:
        return 3
    if role == UserProfile.Role.EMPLOYEE:
        return 2
    return 3


def can_move_task_to_column(user, task, column):
    if not user.is_authenticated or task.project_id != column.project_id:
        return False
    limit = task_move_limit(user, task.project)
    if limit is None:
        return False
    return column.position <= limit


def can_edit_task(user, task):
    if not user.is_authenticated:
        return False
    if is_management(user):
        return True

    role = project_role_for(user, task.project)
    if role == UserProfile.Role.CLIENT:
        return task.column.position == 0
    if role == ProjectAssignment.ProjectRole.LEAD:
        return task.column.position in {0, 1, 2}
    if role == UserProfile.Role.EMPLOYEE:
        return task.column.position in {0, 1}
    return False


def can_delete_task(user, task):
    if not can_edit_task(user, task):
        return False
    return is_management(user) or task.created_by_id == user.id


def can_edit_task_fields(user, task):
    return user.is_authenticated and (is_management(user) or task.created_by_id == user.id)


def can_edit_task_labels(user, task):
    if is_management(user):
        return True
    return user.is_authenticated and task.assignee_id == user.id
