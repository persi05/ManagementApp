from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum
from django.shortcuts import render

from features.accounts.models import UserProfile, ensure_profile, is_management, user_role
from features.projects.selectors import visible_projects
from features.reports.services import employee_month_summaries, month_bounds, payroll_amount
from features.tasks.models import TaskWorklog
from features.tasks.selectors import visible_tasks
from features.time_tracking.models import TimeEntry, WorkSession


def format_timer_seconds(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds // 3600:02}:{(seconds % 3600) // 60:02}:{seconds % 60:02}'


@login_required
def dashboard(request):
    ensure_profile(request.user)
    projects = visible_projects(request.user).prefetch_related('tasks')
    tasks = visible_tasks(request.user)
    start_date, next_month, start_dt, end_dt = month_bounds(request)

    employee_summaries = []
    if is_management(request.user):
        employee_summaries = employee_month_summaries(start_date, next_month, start_dt, end_dt)
        entries = TimeEntry.objects.none()
        worklogs = TaskWorklog.objects.filter(user__profile__role=UserProfile.Role.EMPLOYEE, date__gte=start_date, date__lt=next_month)
    else:
        entries = TimeEntry.objects.filter(user=request.user, start__gte=start_dt, start__lt=end_dt)
        if user_role(request.user) == UserProfile.Role.CLIENT:
            worklogs = TaskWorklog.objects.filter(task__project__in=projects, visible_to_client=True, date__gte=start_date, date__lt=next_month)
        else:
            worklogs = TaskWorklog.objects.filter(user=request.user, date__gte=start_date, date__lt=next_month)

    active_session = WorkSession.objects.filter(user=request.user, state__in=[WorkSession.State.RUNNING, WorkSession.State.PAUSED]).first()
    active_session_seconds = active_session.active_seconds() if active_session else 0
    total_minutes = sum(entry.duration_minutes for entry in entries)
    task_hours = worklogs.aggregate(total=Sum('hours'))['total'] or Decimal('0')
    client_project_rows = []
    if user_role(request.user) == UserProfile.Role.CLIENT:
        for project in projects:
            project_worklogs = worklogs.filter(task__project=project)
            project_hours = project_worklogs.aggregate(total=Sum('hours'))['total'] or Decimal('0')
            task_count = tasks.filter(project=project).count()
            done_count = tasks.filter(project=project, column__name__iexact='Zakonczone').count() + tasks.filter(project=project, column__name__iexact='Zakończone').count()
            client_project_rows.append({
                'project': project,
                'hours': project_hours,
                'task_count': task_count,
                'done_count': done_count,
            })
    notifications = request.user.notifications.filter(is_read=False)[:5]
    current_rate = request.user.hourly_rates.order_by('-valid_from').first()
    payroll = None if is_management(request.user) or user_role(request.user) == UserProfile.Role.CLIENT else payroll_amount(request.user, entries, start_date, next_month)
    team_hours = sum(row['hours'] for row in employee_summaries) if employee_summaries else Decimal('0')

    context = {
        'projects': projects[:6],
        'tasks': tasks[:8],
        'active_session': active_session,
        'active_session_seconds': active_session_seconds,
        'active_session_display': format_timer_seconds(active_session_seconds),
        'total_hours': Decimal(total_minutes) / Decimal(60),
        'task_hours': task_hours,
        'client_project_rows': client_project_rows,
        'client_task_count': sum(row['task_count'] for row in client_project_rows),
        'client_done_count': sum(row['done_count'] for row in client_project_rows),
        'notifications': notifications,
        'current_rate': current_rate,
        'payroll': payroll,
        'employee_summaries': employee_summaries,
        'team_hours': team_hours,
        'team_count': User.objects.filter(profile__role=UserProfile.Role.EMPLOYEE).count(),
        'role': user_role(request.user),
    }
    return render(request, 'features/dashboard.html', context)
