import csv
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AccountForm, EmployeeProfileForm, HourlyRateForm, ProjectAssignmentForm, ProjectForm, RegisterForm, TaskForm, TimeEntryForm, UserRoleForm, WorklogForm
from .models import (
    BoardColumn,
    HourlyRate,
    Notification,
    ProjectAssignment,
    TaskWorklog,
    TimeEntry,
    UserProfile,
    WorkSession,
    ensure_profile,
    is_management,
    user_role,
)
from .selectors import visible_projects, visible_tasks
from .services import employee_month_summaries, ensure_default_columns, month_bounds, payroll_amount


def optional_pk(value):
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def management_required(user):
    if not is_management(user):
        return HttpResponseForbidden('Brak uprawnień.')
    return None


def worker_required(user):
    if user_role(user) == UserProfile.Role.CLIENT:
        return HttpResponseForbidden('Klient nie ma dostępu do rejestracji czasu pracy.')
    return None


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data['email']
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.save()
            profile = ensure_profile(user)
            profile.role = UserProfile.Role.CLIENT
            profile.save()
            login(request, user)
            messages.success(request, 'Konto zostało utworzone.')
            return redirect('dashboard')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
def account_settings(request):
    if request.method == 'POST' and request.POST.get('form') == 'profile':
        account_form = AccountForm(request.POST, instance=request.user)
        password_form = PasswordChangeForm(request.user)
        if account_form.is_valid():
            account_form.save()
            messages.success(request, 'Dane konta zostały zapisane.')
            return redirect('account_settings')
    elif request.method == 'POST' and request.POST.get('form') == 'password':
        account_form = AccountForm(instance=request.user)
        password_form = PasswordChangeForm(request.user, request.POST)
        if password_form.is_valid():
            password_form.save()
            update_session_auth_hash(request, password_form.user)
            messages.success(request, 'Hasło zostało zmienione.')
            return redirect('account_settings')
    else:
        account_form = AccountForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)

    return render(request, 'registration/account_settings.html', {
        'account_form': account_form,
        'password_form': password_form,
    })


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
    return render(request, 'core/dashboard.html', context)


@login_required
def projects(request):
    if request.method == 'POST':
        if not is_management(request.user):
            return HttpResponseForbidden('Brak uprawnień.')
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save()
            if project.client:
                ProjectAssignment.objects.get_or_create(
                    project=project,
                    user=project.client,
                    defaults={'project_role': ProjectAssignment.ProjectRole.CLIENT},
                )
            ensure_default_columns(project)
            messages.success(request, 'Projekt został utworzony.')
            return redirect('projects')
    else:
        form = ProjectForm()
    return render(request, 'core/projects.html', {'projects': visible_projects(request.user), 'form': form, 'can_manage': is_management(request.user)})


@login_required
def project_detail(request, project_id):
    project = get_object_or_404(visible_projects(request.user), pk=project_id)
    assignment_form = ProjectAssignmentForm(project=project)

    if request.method == 'POST':
        forbidden = management_required(request.user)
        if forbidden:
            return forbidden

        assignment_form = ProjectAssignmentForm(request.POST, project=project)
        if assignment_form.is_valid():
            user = assignment_form.cleaned_data['user']
            role = assignment_form.cleaned_data['project_role']
            assignment, created = ProjectAssignment.objects.update_or_create(
                project=project,
                user=user,
                defaults={'project_role': role},
            )
            if role == ProjectAssignment.ProjectRole.CLIENT and project.client_id is None:
                project.client = user
                project.save(update_fields=['client'])
            messages.success(request, 'Użytkownik został przypisany do projektu.' if created else 'Przypisanie zostało zaktualizowane.')
            return redirect('project_detail', project_id=project.id)

    assignments = project.projectassignment_set.select_related('user', 'user__profile').order_by('project_role', 'user__last_name', 'user__username')
    return render(request, 'core/project_detail.html', {
        'project': project,
        'assignments': assignments,
        'assignment_form': assignment_form,
        'can_manage': is_management(request.user),
    })


@login_required
@require_POST
def remove_project_assignment(request, assignment_id):
    forbidden = management_required(request.user)
    if forbidden:
        return forbidden

    assignment = get_object_or_404(ProjectAssignment, pk=assignment_id)
    project_id = assignment.project_id
    assignment.delete()
    messages.success(request, 'Przypisanie zostało usunięte.')
    return redirect('project_detail', project_id=project_id)


@login_required
def kanban(request, project_id=None):
    projects_qs = visible_projects(request.user)
    project = get_object_or_404(projects_qs, pk=project_id) if project_id else projects_qs.first()
    if not project:
        return render(request, 'core/kanban.html', {'project': None, 'projects': projects_qs})
    ensure_default_columns(project)
    if request.method == 'POST':
        form = TaskForm(request.POST)
        form.fields['project'].queryset = projects_qs
        form.fields['column'].queryset = BoardColumn.objects.filter(project__in=projects_qs)
        selected_project_id = optional_pk(request.POST.get('project'))
        if selected_project_id:
            form.fields['assignee'].queryset = User.objects.filter(
                projectassignment__project_id=selected_project_id,
                profile__role=UserProfile.Role.EMPLOYEE,
            ).distinct()
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            task.save()
            messages.success(request, 'Zadanie zostało dodane.')
            return redirect('kanban_project', project_id=task.project_id)
    else:
        form = TaskForm(initial={'project': project})
        form.fields['project'].queryset = projects_qs
        form.fields['column'].queryset = BoardColumn.objects.filter(project=project)
        form.fields['assignee'].queryset = User.objects.filter(
            projectassignment__project=project,
            profile__role=UserProfile.Role.EMPLOYEE,
        ).distinct()
    columns = project.columns.prefetch_related('tasks__assignee', 'tasks__worklogs', 'tasks__checklist')
    return render(request, 'core/kanban.html', {
        'project': project,
        'projects': projects_qs,
        'columns': columns,
        'form': form,
        'can_move_tasks': user_role(request.user) != UserProfile.Role.CLIENT,
    })


@login_required
@require_POST
def move_task(request, task_id):
    if user_role(request.user) == UserProfile.Role.CLIENT:
        return HttpResponseForbidden('Klient nie może zmieniać statusu zadania.')

    task = get_object_or_404(visible_tasks(request.user), pk=task_id)
    column = get_object_or_404(BoardColumn, pk=request.POST.get('column'), project=task.project)
    task.column = column
    task.save(update_fields=['column', 'updated_at'])
    Notification.objects.create(user=task.assignee or request.user, content=f'Zmieniono status zadania: {task.title}', kind='task')
    return JsonResponse({'ok': True, 'column': column.name})


@login_required
def time_entries(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    start_date, next_month, start_dt, end_dt = month_bounds(request)
    if request.method == 'POST':
        form = TimeEntryForm(request.POST)
        form.fields['project'].queryset = visible_projects(request.user)
        form.fields['task'].queryset = visible_tasks(request.user)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            entry.source = TimeEntry.Source.MANUAL
            entry.edited_by = request.user
            entry.edited_at = timezone.now()
            entry.save()
            messages.success(request, 'Wpis czasu został zapisany.')
            return redirect('time_entries')
    else:
        form = TimeEntryForm()
        form.fields['project'].queryset = visible_projects(request.user)
        form.fields['task'].queryset = visible_tasks(request.user)

    qs = TimeEntry.objects.select_related('project', 'task', 'user').filter(start__gte=start_dt, start__lt=end_dt)
    if not is_management(request.user):
        qs = qs.filter(user=request.user)
    return render(request, 'core/time_entries.html', {'entries': qs, 'form': form, 'month': start_date.strftime('%Y-%m')})


@login_required
@require_POST
def start_timer(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    WorkSession.objects.filter(user=request.user, state__in=[WorkSession.State.RUNNING, WorkSession.State.PAUSED]).update(state=WorkSession.State.STOPPED, ended_at=timezone.now())
    project_id = optional_pk(request.POST.get('project'))
    task_id = optional_pk(request.POST.get('task'))
    project = visible_projects(request.user).filter(pk=project_id).first() if project_id else None
    task = visible_tasks(request.user).filter(pk=task_id).first() if task_id else None
    WorkSession.objects.create(user=request.user, project=project, task=task)
    messages.success(request, 'Licznik został uruchomiony.')
    return redirect(request.POST.get('next') or reverse('dashboard'))


@login_required
def employees(request):
    forbidden = management_required(request.user)
    if forbidden:
        return forbidden

    start_date, next_month, start_dt, end_dt = month_bounds(request)
    summaries = employee_month_summaries(start_date, next_month, start_dt, end_dt)
    registered_users = User.objects.select_related('profile').order_by('last_name', 'first_name', 'username')
    return render(request, 'core/employees.html', {
        'employees': summaries,
        'registered_users': registered_users,
        'month': start_date.strftime('%Y-%m'),
        'total_hours': sum(row['hours'] for row in summaries),
        'total_payroll': sum(row['payroll'] for row in summaries),
    })


@login_required
def employee_detail(request, user_id):
    forbidden = management_required(request.user)
    if forbidden:
        return forbidden

    employee = get_object_or_404(User.objects.select_related('profile'), pk=user_id)
    start_date, next_month, start_dt, end_dt = month_bounds(request)

    if request.method == 'POST':
        if request.POST.get('form') == 'role':
            role_form = UserRoleForm(request.POST, instance=employee.profile)
            profile_form = EmployeeProfileForm(instance=employee.profile)
            rate_form = HourlyRateForm()
            if role_form.is_valid():
                role_form.save()
                employee.is_staff = employee.profile.role == UserProfile.Role.MANAGEMENT
                if employee.profile.role != UserProfile.Role.MANAGEMENT:
                    employee.is_superuser = False
                employee.save(update_fields=['is_staff', 'is_superuser'])
                messages.success(request, 'Rola użytkownika została zapisana.')
                return redirect('employee_detail', user_id=employee.id)
        elif request.POST.get('form') == 'profile':
            role_form = UserRoleForm(instance=employee.profile)
            profile_form = EmployeeProfileForm(request.POST, instance=employee.profile)
            rate_form = HourlyRateForm()
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Dane pracownika zapisane.')
                return redirect('employee_detail', user_id=employee.id)
        elif request.POST.get('form') == 'rate':
            role_form = UserRoleForm(instance=employee.profile)
            profile_form = EmployeeProfileForm(instance=employee.profile)
            rate_form = HourlyRateForm(request.POST)
            if rate_form.is_valid():
                rate = rate_form.save(commit=False)
                rate.user = employee
                rate.created_by = request.user
                rate.save()
                messages.success(request, 'Stawka została dodana.')
                return redirect('employee_detail', user_id=employee.id)
        else:
            role_form = UserRoleForm(instance=employee.profile)
            profile_form = EmployeeProfileForm(instance=employee.profile)
            rate_form = HourlyRateForm()
    else:
        role_form = UserRoleForm(instance=employee.profile)
        profile_form = EmployeeProfileForm(instance=employee.profile)
        rate_form = HourlyRateForm()

    entries = list(TimeEntry.objects.filter(user=employee, start__gte=start_dt, start__lt=end_dt).select_related('project', 'task'))
    minutes = sum(entry.duration_minutes for entry in entries)
    rates = HourlyRate.objects.filter(user=employee).order_by('-valid_from')
    return render(request, 'core/employee_detail.html', {
        'employee': employee,
        'entries': entries,
        'month': start_date.strftime('%Y-%m'),
        'hours': Decimal(minutes) / Decimal(60),
        'payroll': payroll_amount(employee, entries, start_date, next_month),
        'rates': rates,
        'profile_form': profile_form,
        'role_form': role_form,
        'rate_form': rate_form,
    })


@login_required
@require_POST
def pause_timer(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    session = get_object_or_404(WorkSession, user=request.user, state=WorkSession.State.RUNNING)
    session.state = WorkSession.State.PAUSED
    session.paused_at = timezone.now()
    session.inactive_minutes += int(request.POST.get('inactive_minutes') or 0)
    session.save()
    messages.info(request, 'Licznik został zatrzymany na pauzie.')
    return redirect(request.POST.get('next') or reverse('dashboard'))


@login_required
@require_POST
def stop_timer(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    session = get_object_or_404(WorkSession, user=request.user, state__in=[WorkSession.State.RUNNING, WorkSession.State.PAUSED])
    now = timezone.now()
    session.state = WorkSession.State.STOPPED
    session.ended_at = now
    session.inactive_minutes += int(request.POST.get('inactive_minutes') or 0)
    session.save()
    local_day_end = timezone.localtime(session.started_at).replace(hour=23, minute=59, second=59, microsecond=999999)
    if now > session.started_at:
        TimeEntry.objects.create(
            user=request.user,
            project=session.project,
            task=session.task,
            start=session.started_at,
            end=now,
            source=TimeEntry.Source.AUTO,
            editable_until=local_day_end,
            inactive_minutes=session.inactive_minutes,
            comment='Utworzone z licznika czasu.',
        )
    messages.success(request, 'Sesja pracy została zakończona i zapisana.')
    return redirect(request.POST.get('next') or reverse('dashboard'))


@login_required
def worklogs(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    if request.method == 'POST':
        form = WorklogForm(request.POST)
        form.fields['task'].queryset = visible_tasks(request.user)
        if form.is_valid():
            worklog = form.save(commit=False)
            worklog.user = request.user
            worklog.save()
            messages.success(request, 'Worklog został dodany.')
            return redirect('worklogs')
    else:
        form = WorklogForm()
        form.fields['task'].queryset = visible_tasks(request.user)

    qs = TaskWorklog.objects.select_related('task', 'task__project', 'user')
    if is_management(request.user):
        pass
    elif user_role(request.user) == UserProfile.Role.CLIENT:
        qs = qs.filter(task__project__in=visible_projects(request.user), visible_to_client=True)
    else:
        qs = qs.filter(user=request.user)
    return render(request, 'core/worklogs.html', {'worklogs': qs[:100], 'form': form, 'role': user_role(request.user)})


@login_required
@require_POST
def toggle_worklog_visibility(request, worklog_id):
    qs = TaskWorklog.objects.all() if is_management(request.user) else TaskWorklog.objects.filter(user=request.user)
    worklog = get_object_or_404(qs, pk=worklog_id)
    worklog.visible_to_client = not worklog.visible_to_client
    worklog.save(update_fields=['visible_to_client'])
    return redirect('worklogs')


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
        return render(request, 'core/reports.html', {
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
    return render(request, 'core/reports.html', {
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
        return render(request, 'core/export_pdf.html', {
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
        return render(request, 'core/export_pdf.html', {
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
    return render(request, 'core/export_pdf.html', {
        'employee': employee,
        'entries': entries,
        'month': start_date.strftime('%Y-%m'),
        'payroll': payroll,
        'bank_account': getattr(getattr(employee, 'profile', None), 'bank_account', ''),
    })
