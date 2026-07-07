from features.accounts.models import UserProfile, is_management, user_role
from features.projects.models import ProjectAssignment

from .models import BoardColumn


DEFAULT_BOARD_COLUMNS = ['Do zrobienia', 'W trakcie', 'Review', 'Zakonczone']


def default_permissions_for_position(position):
    return BoardColumn.default_permissions_for_position(position)


def ensure_default_columns(project):
    for position, name in enumerate(DEFAULT_BOARD_COLUMNS):
        BoardColumn.objects.get_or_create(
            project=project,
            name=name,
            defaults={'position': position, **default_permissions_for_position(position)},
        )


def normalize_column_positions(project):
    for position, column in enumerate(project.columns.order_by('position', 'id')):
        if column.position != position:
            column.position = position
            column.save(update_fields=['position'])


def project_role_for(user, project):
    if is_management(user):
        return UserProfile.Role.MANAGEMENT
    assignment = ProjectAssignment.objects.filter(project=project, user=user).only('project_role').first()
    if assignment:
        return assignment.project_role
    return user_role(user)


def column_permission_field(role, action):
    role_prefix = {
        UserProfile.Role.CLIENT: 'client',
        UserProfile.Role.EMPLOYEE: 'employee',
        ProjectAssignment.ProjectRole.LEAD: 'lead',
    }.get(role)
    if role_prefix is None:
        return None
    return f'{role_prefix}_can_{action}'


def column_allows(role, column, action):
    field_name = column_permission_field(role, action)
    if field_name is None:
        return False
    return bool(getattr(column, field_name, False))


def can_move_to_column(user, project, column):
    if not user.is_authenticated or project.id != column.project_id:
        return False
    if is_management(user):
        return True
    return column_allows(project_role_for(user, project), column, 'move_to')


def can_move_task_to_column(user, task, column):
    if not user.is_authenticated or task.project_id != column.project_id:
        return False
    return can_move_to_column(user, task.project, column)


def can_edit_task(user, task):
    if not user.is_authenticated:
        return False
    if is_management(user):
        return True

    return column_allows(project_role_for(user, task.project), task.column, 'edit_tasks')


def can_delete_task(user, task):
    if not user.is_authenticated:
        return False
    if is_management(user):
        return True
    if task.created_by_id != user.id:
        return False
    role = project_role_for(user, task.project)
    return column_allows(role, task.column, 'delete_tasks')


def can_edit_task_fields(user, task):
    return user.is_authenticated and (is_management(user) or task.created_by_id == user.id)


def can_edit_task_labels(user, task):
    if is_management(user):
        return True
    return user.is_authenticated and task.assignee_id == user.id
