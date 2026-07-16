import csv
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from features.accounts.models import UserProfile, is_management, user_role
from features.projects.models import ProjectLabelRate
from features.projects.selectors import visible_projects
from features.reports.services import date_range_bounds, employee_month_summaries, payroll_amount
from features.tasks.models import TaskWorklog
from features.time_tracking.models import TimeEntry


def project_report_worklogs(user, start_date, end_date, *, selected_project='', selected_client='', selected_employee='', report_visibility='client'):
    projects = visible_projects(user).select_related('client')

    if selected_client:
        projects = projects.filter(
            Q(client_id=selected_client)
            | Q(projectassignment__user_id=selected_client, projectassignment__project_role='client')
        ).distinct()
    if selected_project:
        projects = projects.filter(pk=selected_project)

    worklogs = TaskWorklog.objects.select_related('task', 'task__column', 'task__project', 'task__project__client', 'user').filter(
        task__project__in=projects,
        date__gte=start_date,
        date__lt=end_date,
    )
    if user_role(user) == UserProfile.Role.CLIENT:
        worklogs = worklogs.filter(visible_to_client=True)
    elif is_management(user) and report_visibility == 'client':
        worklogs = worklogs.filter(visible_to_client=True)
    elif not is_management(user):
        worklogs = worklogs.filter(user=user)
    if selected_employee and is_management(user):
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
        worklog.billing_is_due = bool(worklog.task.column.is_done_column)
        worklog.billing_label = billing['label']
        worklog.billing_rate = billing['rate']
        worklog.billing_currency = billing['currency']
        worklog.billing_amount = billing['amount']
    return items


def billing_items_for_scope(worklogs, *, completed_only):
    if not completed_only:
        return worklogs
    return [worklog for worklog in worklogs if worklog.billing_is_due]


def normalized_work_scope(request, role):
    if role != UserProfile.Role.CLIENT:
        return 'all'
    return 'completed' if request.GET.get('work_scope') == 'completed' else 'all'


def project_report_rows(worklogs, projects, decorated_worklogs=None):
    rows = []
    for project in projects:
        project_worklogs = worklogs.filter(task__project=project)
        hours = project_worklogs.aggregate(total=Sum('hours'))['total'] or Decimal('0')
        visible_hours = project_worklogs.filter(visible_to_client=True).aggregate(total=Sum('hours'))['total'] or Decimal('0')
        if hours:
            amount = None
            currency = project.client_rate_currency
            if decorated_worklogs is not None:
                project_items = [item for item in decorated_worklogs if item.task.project_id == project.id]
                if project_items and all(item.billing_amount is not None for item in project_items):
                    currencies = {item.billing_currency for item in project_items}
                    if len(currencies) == 1:
                        amount = sum((item.billing_amount for item in project_items), Decimal('0'))
                        currency = currencies.pop()
            rows.append({
                'project': project,
                'client': project.client,
                'hours': hours,
                'visible_hours': visible_hours,
                'hidden_hours': hours - visible_hours,
                'amount': amount,
                'currency': currency,
                'entries_count': project_worklogs.count(),
            })
    return rows


def amount_totals(worklogs):
    if not worklogs or any(item.billing_amount is None for item in worklogs):
        return []
    totals = {}
    for item in worklogs:
        totals[item.billing_currency] = totals.get(item.billing_currency, Decimal('0')) + item.billing_amount
    return [{'currency': currency, 'amount': amount} for currency, amount in sorted(totals.items())]


def report_time_entries(user, start_dt, end_dt, *, selected_project='', selected_client='', selected_employee='', projects=None):
    entries = TimeEntry.objects.select_related('user', 'project', 'task').filter(start__gte=start_dt, start__lt=end_dt)
    if user_role(user) == UserProfile.Role.CLIENT:
        return entries.none()
    if not is_management(user):
        entries = entries.filter(user=user)
    elif selected_employee:
        entries = entries.filter(user_id=selected_employee)
    if selected_project:
        entries = entries.filter(project_id=selected_project)
    elif selected_client and projects is not None:
        entries = entries.filter(project__in=projects)
    return entries


def employee_report_rows(worklogs):
    rows = []
    employees = User.objects.filter(task_worklogs__in=worklogs).distinct().order_by('last_name', 'first_name', 'username')
    for employee in employees:
        hours = worklogs.filter(user=employee).aggregate(total=Sum('hours'))['total'] or Decimal('0')
        rows.append({'user': employee, 'hours': hours})
    return rows


@login_required
def reports(request):
    start_date, end_exclusive, start_dt, end_dt, end_date = date_range_bounds(request)
    selected_project = request.GET.get('project') or ''
    can_manage = is_management(request.user)
    role = user_role(request.user)
    is_client_report = role == UserProfile.Role.CLIENT
    is_employee_report = role == UserProfile.Role.EMPLOYEE
    work_scope = normalized_work_scope(request, role)
    selected_client = (request.GET.get('client') or '') if can_manage else ''
    selected_employee = (request.GET.get('employee') or '') if can_manage else ''
    report_visibility = request.GET.get('visibility') or 'client'
    if report_visibility not in {'client', 'management'}:
        report_visibility = 'client'
    if not can_manage:
        report_visibility = 'client' if role == UserProfile.Role.CLIENT else 'management'
    worklogs, filtered_projects = project_report_worklogs(
        request.user,
        start_date,
        end_exclusive,
        selected_project=selected_project,
        selected_client=selected_client,
        selected_employee=selected_employee,
        report_visibility=report_visibility,
    )
    all_worklog_count = worklogs.count()
    completed_worklog_count = worklogs.filter(task__column__is_done_column=True).count()
    if work_scope == 'completed':
        worklogs = worklogs.filter(task__column__is_done_column=True)
    include_billing = can_manage or is_client_report
    decorated_worklogs = decorate_worklogs(worklogs, project_rate_map(filtered_projects)) if include_billing else list(worklogs)
    billing_completed_only = is_client_report or (can_manage and report_visibility == 'client')
    billable_worklogs = billing_items_for_scope(decorated_worklogs, completed_only=billing_completed_only) if include_billing else []
    displayed_worklogs = decorated_worklogs[:100]
    project_rows = project_report_rows(worklogs, filtered_projects, billable_worklogs if include_billing else None)
    billing_totals = amount_totals(billable_worklogs) if include_billing else []
    total_amount = billing_totals[0]['amount'] if len(billing_totals) == 1 else None
    report_currency = billing_totals[0]['currency'] if len(billing_totals) == 1 else ''
    total_visible_hours = sum(row['visible_hours'] for row in project_rows)

    visible = visible_projects(request.user)
    selected_project_obj = filtered_projects.first() if selected_project else None
    clients = User.objects.filter(
        Q(profile__role=UserProfile.Role.CLIENT),
        Q(client_projects__in=visible) | Q(projectassignment__project__in=visible, projectassignment__project_role='client'),
    ).distinct().order_by('last_name', 'first_name', 'username')
    employees = User.objects.filter(profile__role=UserProfile.Role.EMPLOYEE).order_by('last_name', 'first_name', 'username') if can_manage else User.objects.filter(pk=request.user.pk)
    time_entries = report_time_entries(
        request.user,
        start_dt,
        end_dt,
        selected_project=selected_project,
        selected_client=selected_client,
        selected_employee=selected_employee,
        projects=filtered_projects,
    )
    employee_entries = list(time_entries[:100]) if not is_client_report else []
    employee_work_hours = Decimal('0')
    employee_payroll = None
    if is_employee_report:
        all_employee_entries = list(time_entries)
        employee_work_hours = sum((entry.hours for entry in all_employee_entries), Decimal('0'))
        employee_payroll = payroll_amount(request.user, all_employee_entries, start_date, end_exclusive)
    summary_employees = employees.filter(pk=selected_employee) if selected_employee else employees
    employee_summaries = employee_month_summaries(
        start_date,
        end_exclusive,
        start_dt,
        end_dt,
        employees=summary_employees,
        entries=time_entries,
    ) if can_manage else []
    total_payroll = sum((row['payroll'] for row in employee_summaries), Decimal('0'))
    total_work_hours = sum((row['hours'] for row in employee_summaries), Decimal('0'))

    return render(request, 'features/reports.html', {
        'client_worklogs': displayed_worklogs,
        'worklog_count': worklogs.count(),
        'all_worklog_count': all_worklog_count,
        'completed_worklog_count': completed_worklog_count,
        'work_scope': work_scope,
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
        'can_manage': can_manage,
        'is_client_report': is_client_report,
        'is_employee_report': is_employee_report,
        'is_management_report': can_manage,
        'show_billing': include_billing,
        'billing_completed_only': billing_completed_only,
        'employee_entries': employee_entries,
        'employee_summaries': employee_summaries,
        'total_payroll': total_payroll,
        'total_work_hours': total_work_hours,
        'employee_work_hours': employee_work_hours,
        'employee_task_hours': sum(row['hours'] for row in project_rows),
        'employee_payroll': employee_payroll,
        'total_hours': sum(row['hours'] for row in project_rows),
        'total_visible_hours': total_visible_hours,
        'total_amount': total_amount,
        'billing_totals': billing_totals,
        'has_completed_worklogs': bool(billable_worklogs),
        'report_currency': report_currency,
    })


@login_required
def export_csv(request):
    start_date, end_exclusive, start_dt, end_dt, end_date = date_range_bounds(request)
    role = user_role(request.user)
    can_manage = is_management(request.user)
    work_scope = normalized_work_scope(request, role)
    selected_project = request.GET.get('project') or ''
    selected_client = (request.GET.get('client') or '') if can_manage else ''
    selected_employee = (request.GET.get('employee') or '') if can_manage else ''
    report_visibility = request.GET.get('visibility') if can_manage else ('client' if role == UserProfile.Role.CLIENT else 'management')
    if role == UserProfile.Role.EMPLOYEE:
        entries = report_time_entries(request.user, start_dt, end_dt, selected_project=selected_project)
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="raport-czasu-{start_date:%Y-%m-%d}-{end_date:%Y-%m-%d}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Data', 'Od', 'Do', 'Godziny', 'Projekt', 'Zadanie', 'Źródło'])
        for entry in entries:
            local_start = timezone.localtime(entry.start)
            local_end = timezone.localtime(entry.end)
            writer.writerow([local_start.date(), local_start.strftime('%H:%M'), local_end.strftime('%H:%M'), f'{entry.hours:.2f}', entry.project.name if entry.project else '', entry.task.title if entry.task else '', entry.get_source_display()])
        return response

    worklogs, projects = project_report_worklogs(request.user, start_date, end_exclusive, selected_project=selected_project, selected_client=selected_client, selected_employee=selected_employee, report_visibility=report_visibility or 'client')
    if work_scope == 'completed':
        worklogs = worklogs.filter(task__column__is_done_column=True)
    show_billing = can_manage or role == UserProfile.Role.CLIENT
    decorated_worklogs = decorate_worklogs(worklogs, project_rate_map(projects)) if show_billing else list(worklogs)
    billing_completed_only = role == UserProfile.Role.CLIENT or (can_manage and (report_visibility or 'client') == 'client')
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="raport-projektow-{start_date:%Y-%m-%d}-{end_date:%Y-%m-%d}.csv"'
    writer = csv.writer(response)
    if can_manage:
        writer.writerow(['Data', 'Pracownik', 'Godziny', 'Projekt', 'Klient', 'Zadanie', 'Stawka', 'Etykieta stawki', 'Kwota', 'Waluta', 'Widoczne dla klienta'])
    elif role == UserProfile.Role.CLIENT:
        writer.writerow(['Data', 'Godziny', 'Projekt', 'Zadanie', 'Stawka', 'Etykieta stawki', 'Kwota', 'Waluta'])
    else:
        writer.writerow(['Data', 'Godziny', 'Projekt', 'Zadanie'])
    for worklog in decorated_worklogs:
        client = worklog.task.project.client
        is_billed = not billing_completed_only or worklog.billing_is_due
        if can_manage:
            writer.writerow([worklog.date, worklog.user.get_full_name() or worklog.user.username, f'{worklog.hours:.2f}', worklog.task.project.name, client.get_full_name() or client.username if client else '', worklog.task.title, f'{worklog.billing_rate:.2f}' if is_billed and worklog.billing_rate is not None else '', worklog.billing_label if is_billed else '', f'{worklog.billing_amount:.2f}' if is_billed and worklog.billing_amount is not None else '', worklog.billing_currency if is_billed else '', 'tak' if worklog.visible_to_client else 'nie'])
        elif role == UserProfile.Role.CLIENT:
            writer.writerow([worklog.date, f'{worklog.hours:.2f}', worklog.task.project.name, worklog.task.title, f'{worklog.billing_rate:.2f}' if is_billed and worklog.billing_rate is not None else '', worklog.billing_label if is_billed else '', f'{worklog.billing_amount:.2f}' if is_billed and worklog.billing_amount is not None else '', worklog.billing_currency if is_billed else ''])
        else:
            writer.writerow([worklog.date, f'{worklog.hours:.2f}', worklog.task.project.name, worklog.task.title])
    return response


@login_required
def export_pdf(request):
    start_date, end_exclusive, start_dt, end_dt, end_date = date_range_bounds(request)

    role = user_role(request.user)
    work_scope = normalized_work_scope(request, role)
    if is_management(request.user) and request.GET.get('report') == 'payroll':
        selected_project = request.GET.get('project') or ''
        selected_client = request.GET.get('client') or ''
        selected_employee = request.GET.get('employee') or ''
        projects = visible_projects(request.user)
        if selected_client:
            projects = projects.filter(Q(client_id=selected_client) | Q(projectassignment__user_id=selected_client, projectassignment__project_role='client')).distinct()
        entries = report_time_entries(request.user, start_dt, end_dt, selected_project=selected_project, selected_client=selected_client, selected_employee=selected_employee, projects=projects)
        employees = User.objects.filter(profile__role=UserProfile.Role.EMPLOYEE)
        if selected_employee:
            employees = employees.filter(pk=selected_employee)
        summaries = employee_month_summaries(start_date, end_exclusive, start_dt, end_dt, employees=employees, entries=entries)
        return render(request, 'features/export_pdf.html', {
            'is_management_summary': True,
            'employees': summaries,
            'entries': entries,
            'month': start_date.strftime('%Y-%m'),
            'period_label': f'{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}',
            'total_hours': sum((row['hours'] for row in summaries), Decimal('0')),
            'total_payroll': sum((row['payroll'] for row in summaries), Decimal('0')),
        })

    if request.GET.get('user') or role == UserProfile.Role.EMPLOYEE:
        employee = request.user
        if is_management(request.user):
            employee = get_object_or_404(User.objects.select_related('profile'), pk=request.GET['user'])
        if employee != request.user and not is_management(request.user):
            return HttpResponseForbidden('Brak uprawnien.')
        entries = TimeEntry.objects.select_related('project', 'task').filter(user=employee, start__gte=start_dt, start__lt=end_dt)
        if request.GET.get('project'):
            entries = entries.filter(project_id=request.GET['project'])
        entries = list(entries)
        payroll = payroll_amount(employee, entries, start_date, end_exclusive)
        return render(request, 'features/export_pdf.html', {
            'employee': employee,
            'entries': entries,
            'month': start_date.strftime('%Y-%m'),
            'period_label': f'{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}',
            'payroll': payroll,
            'bank_account': getattr(getattr(employee, 'profile', None), 'bank_account', ''),
        })

    can_manage = is_management(request.user)
    selected_project = request.GET.get('project') or ''
    selected_client = (request.GET.get('client') or '') if can_manage else ''
    selected_employee = (request.GET.get('employee') or '') if can_manage else ''
    report_visibility = (request.GET.get('visibility') or 'client') if can_manage else 'client'
    worklogs, projects = project_report_worklogs(request.user, start_date, end_exclusive, selected_project=selected_project, selected_client=selected_client, selected_employee=selected_employee, report_visibility=report_visibility)
    if work_scope == 'completed':
        worklogs = worklogs.filter(task__column__is_done_column=True)
    show_billing = can_manage or role == UserProfile.Role.CLIENT
    decorated_worklogs = decorate_worklogs(worklogs, project_rate_map(projects)) if show_billing else list(worklogs)
    billing_completed_only = role == UserProfile.Role.CLIENT or (can_manage and report_visibility == 'client')
    billable_worklogs = billing_items_for_scope(decorated_worklogs, completed_only=billing_completed_only) if show_billing else []
    project_rows = project_report_rows(worklogs, projects, billable_worklogs if show_billing else None)
    billing_totals = amount_totals(billable_worklogs) if show_billing else []
    total_amount = billing_totals[0]['amount'] if len(billing_totals) == 1 else None
    return render(request, 'features/export_pdf.html', {
        'is_client_summary': True,
        'show_billing': show_billing,
        'billing_completed_only': billing_completed_only,
        'is_client_export': role == UserProfile.Role.CLIENT,
        'report_visibility': report_visibility,
        'work_scope': work_scope,
        'worklogs': decorated_worklogs,
        'by_project': project_rows,
        'month': start_date.strftime('%Y-%m'),
        'period_label': f'{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}',
        'total_hours': sum(row['hours'] for row in project_rows),
        'total_amount': total_amount,
        'billing_totals': billing_totals,
        'has_completed_worklogs': bool(billable_worklogs),
        'report_currency': billing_totals[0]['currency'] if len(billing_totals) == 1 else '',
    })
