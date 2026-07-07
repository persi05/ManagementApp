import csv
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from features.accounts.models import UserProfile, is_management, user_role
from features.projects.selectors import visible_projects
from features.reports.services import date_range_bounds, employee_month_summaries, payroll_amount
from features.tasks.models import TaskWorklog
from features.time_tracking.models import TimeEntry


def project_report_worklogs(request, start_date, end_date):
    selected_project = request.GET.get('project') or ''
    selected_client = request.GET.get('client') or ''
    selected_employee = request.GET.get('employee') or ''
    projects = visible_projects(request.user).select_related('client')

    if selected_client:
        projects = projects.filter(Q(client_id=selected_client) | Q(projectassignment__user_id=selected_client)).distinct()
    if selected_project:
        projects = projects.filter(pk=selected_project)

    worklogs = TaskWorklog.objects.select_related('task', 'task__project', 'task__project__client', 'user').filter(
        task__project__in=projects,
        date__gte=start_date,
        date__lt=end_date,
    )
    if user_role(request.user) == UserProfile.Role.CLIENT:
        worklogs = worklogs.filter(visible_to_client=True)
    elif not is_management(request.user):
        worklogs = worklogs.filter(user=request.user)
    if selected_employee:
        worklogs = worklogs.filter(user_id=selected_employee)

    return worklogs, projects


def project_report_rows(worklogs, projects):
    rows = []
    for project in projects:
        project_worklogs = worklogs.filter(task__project=project)
        hours = project_worklogs.aggregate(total=Sum('hours'))['total'] or Decimal('0')
        if hours:
            rows.append({
                'project': project,
                'client': project.client,
                'hours': hours,
                'entries_count': project_worklogs.count(),
            })
    return rows


def employee_report_rows(worklogs):
    rows = []
    employees = User.objects.filter(task_worklogs__in=worklogs).distinct().order_by('last_name', 'first_name', 'username')
    for employee in employees:
        hours = worklogs.filter(user=employee).aggregate(total=Sum('hours'))['total'] or Decimal('0')
        rows.append({'user': employee, 'hours': hours})
    return rows


@login_required
def reports(request):
    start_date, end_exclusive, _start_dt, _end_dt, end_date = date_range_bounds(request)
    selected_project = request.GET.get('project') or ''
    selected_client = request.GET.get('client') or ''
    selected_employee = request.GET.get('employee') or ''
    worklogs, filtered_projects = project_report_worklogs(request, start_date, end_exclusive)
    project_rows = project_report_rows(worklogs, filtered_projects)

    visible = visible_projects(request.user)
    clients = User.objects.filter(
        Q(profile__role=UserProfile.Role.CLIENT),
        Q(client_projects__in=visible) | Q(projectassignment__project__in=visible, projectassignment__project_role='client'),
    ).distinct().order_by('last_name', 'first_name', 'username')
    employees = User.objects.filter(profile__role=UserProfile.Role.EMPLOYEE).order_by('last_name', 'first_name', 'username') if is_management(request.user) else User.objects.filter(pk=request.user.pk)

    return render(request, 'features/reports.html', {
        'client_worklogs': worklogs[:100],
        'by_user': employee_report_rows(worklogs),
        'by_project': project_rows,
        'month': start_date.strftime('%Y-%m'),
        'date_from': start_date.isoformat(),
        'date_to': end_date.isoformat(),
        'period_label': f'{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}',
        'projects': visible.select_related('client'),
        'clients': clients,
        'employees': employees,
        'selected_project': selected_project,
        'selected_client': selected_client,
        'selected_employee': selected_employee,
        'selected_user': selected_employee,
        'can_manage': is_management(request.user),
        'is_client_report': user_role(request.user) == UserProfile.Role.CLIENT,
        'total_hours': sum(row['hours'] for row in project_rows),
    })


@login_required
def export_csv(request):
    start_date, end_exclusive, _start_dt, _end_dt, end_date = date_range_bounds(request)
    worklogs, _projects = project_report_worklogs(request, start_date, end_exclusive)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="raport-projektow-{start_date:%Y-%m-%d}-{end_date:%Y-%m-%d}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Data', 'Pracownik', 'Godziny', 'Projekt', 'Klient', 'Zadanie', 'Komentarz', 'Widoczne dla klienta'])
    for worklog in worklogs:
        client = worklog.task.project.client
        writer.writerow([
            worklog.date,
            worklog.user.get_full_name() or worklog.user.username,
            f'{worklog.hours:.2f}',
            worklog.task.project.name,
            client.get_full_name() or client.username if client else '',
            worklog.task.title,
            worklog.comment,
            'tak' if worklog.visible_to_client else 'nie',
        ])
    return response


@login_required
def export_pdf(request):
    start_date, end_exclusive, start_dt, end_dt, end_date = date_range_bounds(request)

    if request.GET.get('user'):
        employee = request.user
        if is_management(request.user):
            employee = get_object_or_404(User.objects.select_related('profile'), pk=request.GET['user'])
        if employee != request.user and not is_management(request.user):
            return HttpResponseForbidden('Brak uprawnien.')
        entries = list(TimeEntry.objects.select_related('project', 'task').filter(user=employee, start__gte=start_dt, start__lt=end_dt))
        payroll = payroll_amount(employee, entries, start_date, end_exclusive)
        return render(request, 'features/export_pdf.html', {
            'employee': employee,
            'entries': entries,
            'month': start_date.strftime('%Y-%m'),
            'period_label': f'{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}',
            'payroll': payroll,
            'bank_account': getattr(getattr(employee, 'profile', None), 'bank_account', ''),
        })

    worklogs, projects = project_report_worklogs(request, start_date, end_exclusive)
    project_rows = project_report_rows(worklogs, projects)
    return render(request, 'features/export_pdf.html', {
        'is_client_summary': True,
        'worklogs': worklogs,
        'by_project': project_rows,
        'month': start_date.strftime('%Y-%m'),
        'period_label': f'{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}',
        'total_hours': sum(row['hours'] for row in project_rows),
    })
