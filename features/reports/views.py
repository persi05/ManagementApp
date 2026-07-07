import csv
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from features.accounts.models import UserProfile, is_management, user_role
from features.projects.selectors import visible_projects
from features.reports.services import employee_month_summaries, month_bounds, payroll_amount
from features.tasks.models import TaskWorklog
from features.time_tracking.models import TimeEntry


@login_required
def reports(request):
    start_date, next_month, start_dt, end_dt = month_bounds(request)
    user_id = request.GET.get('user')
    if user_role(request.user) == UserProfile.Role.CLIENT:
        worklogs = TaskWorklog.objects.select_related('task', 'task__project', 'user').filter(
            task__project__in=visible_projects(request.user),
            visible_to_client=True,
            date__gte=start_date,
            date__lt=next_month,
        )
        project_rows = []
        for project in visible_projects(request.user):
            project_hours = worklogs.filter(task__project=project).aggregate(total=Sum('hours'))['total'] or Decimal('0')
            if project_hours:
                project_rows.append({'project': project, 'hours': project_hours})
        return render(request, 'features/reports.html', {
            'entries': [],
            'client_worklogs': worklogs[:100],
            'by_user': [],
            'by_project': project_rows,
            'month': start_date.strftime('%Y-%m'),
            'employees': User.objects.none(),
            'selected_user': '',
            'can_manage': False,
            'is_client_report': True,
        })

    entries = TimeEntry.objects.select_related('user', 'project', 'task').filter(start__gte=start_dt, start__lt=end_dt)
    if is_management(request.user) and user_id:
        entries = entries.filter(user_id=user_id)
    elif not is_management(request.user):
        entries = entries.filter(user=request.user)

    users = User.objects.filter(profile__role=UserProfile.Role.EMPLOYEE) if is_management(request.user) else User.objects.filter(pk=request.user.pk)
    by_user = []
    for employee in users:
        user_entries = list(entries.filter(user=employee))
        minutes = sum(item.duration_minutes for item in user_entries)
        by_user.append({
            'user': employee,
            'hours': Decimal(minutes) / Decimal(60),
            'payroll': payroll_amount(employee, user_entries, start_date, next_month),
            'bank_account': getattr(getattr(employee, 'profile', None), 'bank_account', ''),
        })
    project_rows = []
    for project in visible_projects(request.user):
        project_entries = entries.filter(project=project)
        minutes = sum(item.duration_minutes for item in project_entries)
        if minutes:
            project_rows.append({'project': project, 'hours': Decimal(minutes) / Decimal(60)})
    return render(request, 'features/reports.html', {
        'entries': entries[:100],
        'by_user': by_user,
        'by_project': project_rows,
        'month': start_date.strftime('%Y-%m'),
        'employees': users,
        'selected_user': user_id or '',
        'can_manage': is_management(request.user),
    })


@login_required
def export_csv(request):
    start_date, next_month, start_dt, end_dt = month_bounds(request)
    if user_role(request.user) == UserProfile.Role.CLIENT:
        worklogs = TaskWorklog.objects.select_related('task', 'task__project', 'user').filter(
            task__project__in=visible_projects(request.user),
            visible_to_client=True,
            date__gte=start_date,
            date__lt=next_month,
        )
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="raport-klienta-{start_date:%Y-%m}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Data', 'Godziny', 'Projekt', 'Zadanie', 'Komentarz'])
        for worklog in worklogs:
            writer.writerow([worklog.date, f'{worklog.hours:.2f}', worklog.task.project.name, worklog.task.title, worklog.comment])
        return response

    entries = TimeEntry.objects.select_related('user', 'project', 'task').filter(start__gte=start_dt, start__lt=end_dt)
    if not is_management(request.user):
        entries = entries.filter(user=request.user)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="czas-pracy-{start_date:%Y-%m}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Pracownik', 'Data', 'Start', 'Koniec', 'Godziny', 'Projekt', 'Zadanie', 'Źródło'])
    for entry in entries:
        writer.writerow([
            entry.user.get_full_name() or entry.user.username,
            timezone.localtime(entry.start).date(),
            timezone.localtime(entry.start).time().strftime('%H:%M'),
            timezone.localtime(entry.end).time().strftime('%H:%M'),
            f'{entry.hours:.2f}',
            entry.project.name if entry.project else '',
            entry.task.title if entry.task else '',
            entry.get_source_display(),
        ])
    return response


@login_required
def export_pdf(request):
    start_date, next_month, start_dt, end_dt = month_bounds(request)
    if user_role(request.user) == UserProfile.Role.CLIENT:
        worklogs = TaskWorklog.objects.select_related('task', 'task__project').filter(
            task__project__in=visible_projects(request.user),
            visible_to_client=True,
            date__gte=start_date,
            date__lt=next_month,
        )
        project_rows = []
        for project in visible_projects(request.user):
            project_hours = worklogs.filter(task__project=project).aggregate(total=Sum('hours'))['total'] or Decimal('0')
            if project_hours:
                project_rows.append({'project': project, 'hours': project_hours})
        return render(request, 'features/export_pdf.html', {
            'is_client_summary': True,
            'worklogs': worklogs,
            'by_project': project_rows,
            'month': start_date.strftime('%Y-%m'),
            'total_hours': sum(row['hours'] for row in project_rows),
        })

    if is_management(request.user) and not request.GET.get('user'):
        summaries = employee_month_summaries(start_date, next_month, start_dt, end_dt)
        entries = TimeEntry.objects.select_related('user', 'project', 'task').filter(
            user__profile__role=UserProfile.Role.EMPLOYEE,
            start__gte=start_dt,
            start__lt=end_dt,
        )
        return render(request, 'features/export_pdf.html', {
            'is_management_summary': True,
            'employees': summaries,
            'entries': entries,
            'month': start_date.strftime('%Y-%m'),
            'total_hours': sum(row['hours'] for row in summaries),
            'total_payroll': sum(row['payroll'] for row in summaries),
        })

    employee = request.user
    if is_management(request.user) and request.GET.get('user'):
        employee = get_object_or_404(User.objects.select_related('profile'), pk=request.GET['user'])
    if employee != request.user and not is_management(request.user):
        return HttpResponseForbidden('Brak uprawnień.')
    entries = list(TimeEntry.objects.select_related('project', 'task').filter(user=employee, start__gte=start_dt, start__lt=end_dt))
    payroll = payroll_amount(employee, entries, start_date, next_month)
    return render(request, 'features/export_pdf.html', {
        'employee': employee,
        'entries': entries,
        'month': start_date.strftime('%Y-%m'),
        'payroll': payroll,
        'bank_account': getattr(getattr(employee, 'profile', None), 'bank_account', ''),
    })
