import csv
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from features.accounts.models import UserProfile, is_management, user_role
from features.projects.models import ProjectLabelRate
from features.projects.selectors import visible_projects
from features.reports.services import date_range_bounds, employee_month_summaries, payroll_amount
from features.tasks.models import TaskWorklog
from features.time_tracking.models import TimeEntry


def project_report_worklogs(request, start_date, end_date):
    selected_project = request.GET.get('project') or ''
    selected_client = request.GET.get('client') or ''
    selected_employee = request.GET.get('employee') or ''
    report_visibility = request.GET.get('visibility') or 'client'
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
    elif is_management(request.user) and report_visibility == 'client':
        worklogs = worklogs.filter(visible_to_client=True)
    elif not is_management(request.user):
        worklogs = worklogs.filter(user=request.user)
    if selected_employee:
        worklogs = worklogs.filter(user_id=selected_employee)

    return worklogs, projects


def project_rate_map(projects):
    rates = {}
    for rate in ProjectLabelRate.objects.filter(project__in=projects):
        rates.setdefault(rate.project_id, {})[rate.label.strip().lower()] = rate
    return rates


def billing_for_worklog(worklog, rates_by_project):
    project = worklog.task.project
    label_rates = rates_by_project.get(project.id, {})
    labels = [label.strip().lower() for label in worklog.task.labels.split(',') if label.strip()]
    for label in labels:
        rate = label_rates.get(label)
        if rate:
            return {
                'label': rate.label,
                'rate': rate.hourly_rate,
                'currency': rate.currency,
                'amount': worklog.hours * rate.hourly_rate,
            }

    if project.client_hourly_rate is not None:
        return {
            'label': '',
            'rate': project.client_hourly_rate,
            'currency': project.client_rate_currency,
            'amount': worklog.hours * project.client_hourly_rate,
        }

    return {'label': '', 'rate': None, 'currency': project.client_rate_currency, 'amount': None}


def decorate_worklogs(worklogs, rates_by_project):
    items = list(worklogs)
    for worklog in items:
        billing = billing_for_worklog(worklog, rates_by_project)
        worklog.billing_label = billing['label']
        worklog.billing_rate = billing['rate']
        worklog.billing_currency = billing['currency']
        worklog.billing_amount = billing['amount']
    return items


def project_report_rows(worklogs, projects, decorated_worklogs=None, visible_amount_only=True):
    rows = []
    for project in projects:
        project_worklogs = worklogs.filter(task__project=project)
        hours = project_worklogs.aggregate(total=Sum('hours'))['total'] or Decimal('0')
        visible_hours = project_worklogs.filter(visible_to_client=True).aggregate(total=Sum('hours'))['total'] or Decimal('0')
        if hours:
            amount = Decimal('0')
            currency = project.client_rate_currency
            if decorated_worklogs is not None:
                project_items = [item for item in decorated_worklogs if item.task.project_id == project.id]
                if visible_amount_only:
                    project_items = [item for item in project_items if item.visible_to_client]
                if project_items and all(item.billing_amount is not None for item in project_items):
                    amount = sum(item.billing_amount for item in project_items)
                    currency = project_items[0].billing_currency
                elif project_items:
                    amount = None
            rows.append({
                'project': project,
                'client': project.client,
                'hours': hours,
                'visible_hours': visible_hours,
                'amount': amount,
                'currency': currency,
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
    report_visibility = request.GET.get('visibility') or 'client'
    if not is_management(request.user):
        report_visibility = 'client' if user_role(request.user) == UserProfile.Role.CLIENT else 'management'
    worklogs, filtered_projects = project_report_worklogs(request, start_date, end_exclusive)
    rates_by_project = project_rate_map(filtered_projects)
    decorated_worklogs = decorate_worklogs(worklogs, rates_by_project)
    client_worklogs = decorated_worklogs[:100]
    project_rows = project_report_rows(
        worklogs,
        filtered_projects,
        decorated_worklogs,
        visible_amount_only=report_visibility == 'client',
    )
    total_amount = Decimal('0')
    if all(row['amount'] is not None for row in project_rows):
        total_amount = sum(row['amount'] for row in project_rows)
    else:
        total_amount = None
    total_visible_hours = sum(row['visible_hours'] for row in project_rows)

    visible = visible_projects(request.user)
    selected_project_obj = filtered_projects.first() if selected_project else None
    clients = User.objects.filter(
        Q(profile__role=UserProfile.Role.CLIENT),
        Q(client_projects__in=visible) | Q(projectassignment__project__in=visible, projectassignment__project_role='client'),
    ).distinct().order_by('last_name', 'first_name', 'username')
    employees = User.objects.filter(profile__role=UserProfile.Role.EMPLOYEE).order_by('last_name', 'first_name', 'username') if is_management(request.user) else User.objects.filter(pk=request.user.pk)

    return render(request, 'features/reports.html', {
        'client_worklogs': client_worklogs,
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
        'selected_project_obj': selected_project_obj,
        'selected_client': selected_client,
        'selected_employee': selected_employee,
        'selected_user': selected_employee,
        'report_visibility': report_visibility,
        'is_client_visibility_report': report_visibility == 'client',
        'can_manage': is_management(request.user),
        'is_client_report': user_role(request.user) == UserProfile.Role.CLIENT,
        'total_hours': sum(row['hours'] for row in project_rows),
        'total_visible_hours': total_visible_hours,
        'total_amount': total_amount,
        'report_currency': project_rows[0]['currency'] if project_rows else 'PLN',
    })


@login_required
def export_csv(request):
    start_date, end_exclusive, _start_dt, _end_dt, end_date = date_range_bounds(request)
    worklogs, projects = project_report_worklogs(request, start_date, end_exclusive)
    rates_by_project = project_rate_map(projects)
    decorated_worklogs = decorate_worklogs(worklogs, rates_by_project)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="raport-projektow-{start_date:%Y-%m-%d}-{end_date:%Y-%m-%d}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Data', 'Pracownik', 'Godziny', 'Projekt', 'Klient', 'Zadanie', 'Stawka', 'Etykieta stawki', 'Kwota', 'Waluta', 'Komentarz', 'Widoczne dla klienta'])
    for worklog in decorated_worklogs:
        client = worklog.task.project.client
        writer.writerow([
            worklog.date,
            worklog.user.get_full_name() or worklog.user.username,
            f'{worklog.hours:.2f}',
            worklog.task.project.name,
            client.get_full_name() or client.username if client else '',
            worklog.task.title,
            f'{worklog.billing_rate:.2f}' if worklog.billing_rate is not None else '',
            worklog.billing_label,
            f'{worklog.billing_amount:.2f}' if worklog.billing_amount is not None else '',
            worklog.billing_currency,
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
    rates_by_project = project_rate_map(projects)
    decorated_worklogs = decorate_worklogs(worklogs, rates_by_project)
    report_visibility = request.GET.get('visibility') or 'client'
    project_rows = project_report_rows(
        worklogs,
        projects,
        decorated_worklogs,
        visible_amount_only=report_visibility == 'client',
    )
    total_amount = Decimal('0')
    if all(row['amount'] is not None for row in project_rows):
        total_amount = sum(row['amount'] for row in project_rows)
    else:
        total_amount = None
    return render(request, 'features/export_pdf.html', {
        'is_client_summary': True,
        'report_visibility': report_visibility,
        'worklogs': decorated_worklogs,
        'by_project': project_rows,
        'month': start_date.strftime('%Y-%m'),
        'period_label': f'{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}',
        'total_hours': sum(row['hours'] for row in project_rows),
        'total_amount': total_amount,
        'report_currency': project_rows[0]['currency'] if project_rows else 'PLN',
    })
