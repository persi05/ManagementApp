from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from features.accounts.models import UserProfile, is_management, user_role
from features.projects.models import ProjectAssignment

from .models import BoardColumn, Notification, Task


DEFAULT_BOARD_COLUMNS = ['Do zrobienia', 'W trakcie', 'Review', 'Zakończone']


def default_permissions_for_position(position):
    return BoardColumn.default_permissions_for_position(position)


def ensure_default_columns(project):
    for position, name in enumerate(DEFAULT_BOARD_COLUMNS):
        BoardColumn.objects.get_or_create(
            project=project,
            name=name,
            defaults={
                'position': position,
                'is_done_column': position == len(DEFAULT_BOARD_COLUMNS) - 1,
                **default_permissions_for_position(position),
            },
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


def can_view_column(user, project, column):
    if not user.is_authenticated or project.id != column.project_id:
        return False
    if is_management(user):
        return True
    return column_allows(project_role_for(user, project), column, 'view_column')


def visible_columns(user, project):
    columns = project.columns.all()
    if is_management(user):
        return columns

    role = project_role_for(user, project)
    field_name = column_permission_field(role, 'view_column')
    if field_name is None:
        return columns.none()
    return columns.filter(**{field_name: True})


def can_create_task_in_column(user, project, column):
    if not user.is_authenticated or project.id != column.project_id:
        return False
    if is_management(user):
        return True
    return can_view_column(user, project, column) and column_allows(project_role_for(user, project), column, 'create_tasks')


def can_move_to_column(user, project, column):
    if not user.is_authenticated or project.id != column.project_id:
        return False
    if is_management(user):
        return True
    return can_view_column(user, project, column) and column_allows(project_role_for(user, project), column, 'move_to')


def can_move_task_to_column(user, task, column):
    if not user.is_authenticated or task.project_id != column.project_id:
        return False
    return can_edit_task(user, task) and can_move_to_column(user, task.project, column)


def can_edit_task(user, task):
    if not user.is_authenticated:
        return False
    if is_management(user):
        return True
    return can_view_column(user, task.project, task.column) and column_allows(project_role_for(user, task.project), task.column, 'edit_tasks')


def can_delete_task(user, task):
    if not user.is_authenticated:
        return False
    if is_management(user):
        return True
    role = project_role_for(user, task.project)
    return can_view_column(user, task.project, task.column) and column_allows(role, task.column, 'delete_tasks')


def can_edit_task_fields(user, task):
    return can_edit_task(user, task)


def can_edit_task_labels(user, task):
    if is_management(user):
        return True
    return user.is_authenticated and project_role_for(user, task.project) == ProjectAssignment.ProjectRole.LEAD


def task_assignees(task):
    assigned = list(task.assignees.all())
    if assigned:
        return assigned
    return [task.assignee] if task.assignee_id else []


def notify_task_assignees(task, title, content, kind='task', url='', actor=None, exclude_ids=None):
    exclude_ids = set(exclude_ids or [])
    notifications = []
    for user in task_assignees(task):
        if user.id in exclude_ids:
            continue
        notification = notify_user(user, title, content, kind=kind, url=url, actor=actor)
        if notification:
            notifications.append(notification)
    return notifications


def notify_user(user, title, content, kind='system', url='', actor=None):
    if not user or not getattr(user, 'is_active', True):
        return None
    if actor and getattr(actor, 'id', None) == user.id:
        return None
    return Notification.objects.create(
        user=user,
        title=title,
        content=content,
        kind=kind,
        url=url,
    )


def notify_management(title, content, kind='system', url='', actor=None):
    users = get_user_model().objects.filter(
        Q(profile__role=UserProfile.Role.MANAGEMENT) | Q(is_superuser=True),
        is_active=True,
    ).distinct()
    notifications = []
    for user in users:
        notification = notify_user(user, title, content, kind=kind, url=url, actor=actor)
        if notification:
            notifications.append(notification)
    return notifications


def project_client_users(project):
    user_ids = set()
    if project.client_id:
        user_ids.add(project.client_id)
    user_ids.update(ProjectAssignment.objects.filter(
        project=project,
        project_role=ProjectAssignment.ProjectRole.CLIENT,
    ).values_list('user_id', flat=True))
    return get_user_model().objects.filter(id__in=user_ids, is_active=True)


def notify_project_clients(project, title, content, kind='client_task', url='', actor=None):
    notifications = []
    for user in project_client_users(project):
        notification = notify_user(user, title, content, kind=kind, url=url, actor=actor)
        if notification:
            notifications.append(notification)
    return notifications


def is_first_project_column(task):
    first_column = task.project.columns.order_by('position', 'id').first()
    return bool(first_column and task.column_id == first_column.id)


def is_last_project_column(project, column):
    last_column = project.columns.order_by('-position', '-id').first()
    return bool(last_column and column.id == last_column.id)


def notification_exists_today(user, title, content, kind, url):
    return Notification.objects.filter(
        user=user,
        title=title,
        content=content,
        kind=kind,
        url=url,
        created_at__date=timezone.localdate(),
    ).exists()


def notify_user_once_today(user, title, content, kind='system', url=''):
    if notification_exists_today(user, title, content, kind, url):
        return None
    return notify_user(user, title, content, kind=kind, url=url)


def create_daily_reminders(user):
    if not user.is_authenticated or user_role(user) == UserProfile.Role.CLIENT:
        return

    today = timezone.localdate()
    cache_key = f'daily-reminders:{user.id}:{today:%Y-%m-%d}'
    reminder_kinds = ['task_deadline', 'leave_reminder']
    if cache.get(cache_key) and Notification.objects.filter(user=user, kind__in=reminder_kinds, created_at__date=today).exists():
        return

    tomorrow = today + timedelta(days=1)
    tasks = Task.objects.filter(Q(assignee=user) | Q(assignees=user), due_date=tomorrow).select_related('project').distinct()[:20]
    for task in tasks:
        notify_user_once_today(
            user,
            'Deadline jutro',
            f'Jutro mija termin zadania: {task.title}',
            kind='task_deadline',
            url=reverse('edit_task', args=[task.id]),
        )

    from features.planner.models import LeaveRequest

    leaves = LeaveRequest.objects.filter(
        user=user,
        status=LeaveRequest.Status.APPROVED,
        start_date=tomorrow,
    )[:5]
    for leave_request in leaves:
        notify_user_once_today(
            user,
            'Wolne jutro',
            f'Jutro zaczyna się Twoje wolne: {leave_request.start_date:%Y-%m-%d} - {leave_request.end_date:%Y-%m-%d}',
            kind='leave_reminder',
            url=f"{reverse('calendar')}?month={leave_request.start_date:%Y-%m}",
        )

    cache.set(cache_key, True, 60 * 60 * 12)


def task_label_rate_map(task):
    return {
        rate.label.strip().lower(): rate
        for rate in task.project.label_rates.all()
    }


def task_label_badges(task):
    rates = task_label_rate_map(task)
    badges = []
    for label in task.labels_list:
        rate = rates.get(label.strip().lower())
        badges.append({
            'name': label,
            'rate': rate.hourly_rate if rate else None,
            'currency': rate.currency if rate else task.project.client_rate_currency,
        })
    return badges


def task_effective_client_rate(task):
    rates = task_label_rate_map(task)
    for label in task.labels_list:
        rate = rates.get(label.strip().lower())
        if rate:
            return {
                'label': rate.label,
                'rate': rate.hourly_rate,
                'currency': rate.currency,
            }
    if task.project.client_hourly_rate is not None:
        return {
            'label': '',
            'rate': task.project.client_hourly_rate,
            'currency': task.project.client_rate_currency,
        }
    return None
