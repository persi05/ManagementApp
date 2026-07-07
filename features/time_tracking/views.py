from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from features.accounts.models import is_management
from features.accounts.permissions import optional_pk, worker_required
from features.projects.selectors import visible_projects
from features.reports.services import month_bounds
from features.tasks.selectors import visible_tasks
from features.time_tracking.forms import TimeEntryForm
from features.time_tracking.models import TimeEntry, WorkSession, employee_time_entry_edit_deadline


def format_seconds(seconds):
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60
    return f'{hours:02}:{minutes:02}:{remaining_seconds:02}'


def posted_inactive_seconds(request):
    if request.POST.get('inactive_seconds'):
        return max(0, int(request.POST.get('inactive_seconds') or 0))
    return max(0, int(request.POST.get('inactive_minutes') or 0)) * 60


def paused_seconds(session, now=None):
    if session.state != WorkSession.State.PAUSED or not session.paused_at:
        return 0
    now = now or timezone.now()
    return max(0, int((now - session.paused_at).total_seconds()))


def timer_payload(user):
    session = WorkSession.objects.filter(user=user, state__in=[WorkSession.State.RUNNING, WorkSession.State.PAUSED]).first()
    if not session:
        return {
            'active': False,
            'state': 'stopped',
            'state_label': 'Nieaktywny',
            'active_seconds': 0,
            'display': format_seconds(0),
        }

    active_seconds = session.active_seconds()
    return {
        'active': True,
        'state': session.state,
        'state_label': session.get_state_display(),
        'active_seconds': active_seconds,
        'display': format_seconds(active_seconds),
        'started_at': session.started_at.isoformat(),
        'paused_at': session.paused_at.isoformat() if session.paused_at else None,
        'inactive_seconds': session.total_inactive_seconds,
    }


@login_required
def time_entries(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    start_date, next_month, start_dt, end_dt = month_bounds(request)
    if request.method == 'POST':
        form = TimeEntryForm(request.POST)
        form.fields['project'].queryset = visible_projects(request.user)
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

    qs = TimeEntry.objects.select_related('project', 'task', 'user').filter(start__gte=start_dt, start__lt=end_dt)
    if not is_management(request.user):
        qs = qs.filter(user=request.user)
    entries = list(qs)
    total_hours = sum((entry.hours for entry in entries), Decimal('0'))
    for entry in entries:
        entry.can_edit = entry.can_be_edited_by(request.user)
    return render(request, 'features/time_entries.html', {
        'entries': entries,
        'form': form,
        'month': start_date.strftime('%Y-%m'),
        'total_hours': total_hours,
    })


@login_required
def edit_time_entry(request, entry_id):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    qs = TimeEntry.objects.select_related('project', 'task', 'user')
    if not is_management(request.user):
        qs = qs.filter(user=request.user)
    entry = get_object_or_404(qs, pk=entry_id)
    if not entry.can_be_edited_by(request.user):
        return HttpResponseForbidden('Nie mozna juz edytowac tego wpisu czasu pracy.')

    if request.method == 'POST':
        form = TimeEntryForm(request.POST, instance=entry)
        form.fields['project'].queryset = visible_projects(request.user)
        if form.is_valid():
            updated_entry = form.save(commit=False)
            updated_entry.edited_by = request.user
            updated_entry.edited_at = timezone.now()
            updated_entry.save()
            messages.success(request, 'Wpis czasu pracy zostal zaktualizowany.')
            return redirect('time_entries')
    else:
        form = TimeEntryForm(instance=entry)
        form.fields['project'].queryset = visible_projects(request.user)

    return render(request, 'features/time_entry_edit.html', {'entry': entry, 'form': form})


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
def timer_status(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden
    return JsonResponse(timer_payload(request.user))


@login_required
@require_POST
def pause_timer(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    session = get_object_or_404(WorkSession, user=request.user, state=WorkSession.State.RUNNING)
    session.state = WorkSession.State.PAUSED
    session.paused_at = timezone.now()
    session.set_inactive_seconds(session.total_inactive_seconds + posted_inactive_seconds(request))
    session.save(update_fields=['state', 'paused_at', 'inactive_minutes', 'inactive_seconds'])
    messages.info(request, 'Licznik został zatrzymany na pauzie.')
    return redirect(request.POST.get('next') or reverse('dashboard'))


@login_required
@require_POST
def resume_timer(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    session = get_object_or_404(WorkSession, user=request.user, state=WorkSession.State.PAUSED)
    session.set_inactive_seconds(session.total_inactive_seconds + paused_seconds(session))
    session.state = WorkSession.State.RUNNING
    session.paused_at = None
    session.save(update_fields=['inactive_minutes', 'inactive_seconds', 'state', 'paused_at'])
    messages.success(request, 'Licznik został wznowiony.')
    return redirect(request.POST.get('next') or reverse('dashboard'))


@login_required
@require_POST
def stop_timer(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    session = get_object_or_404(WorkSession, user=request.user, state__in=[WorkSession.State.RUNNING, WorkSession.State.PAUSED])
    now = timezone.now()
    pause_seconds = paused_seconds(session, now)
    session.state = WorkSession.State.STOPPED
    session.ended_at = now
    session.set_inactive_seconds(session.total_inactive_seconds + posted_inactive_seconds(request) + pause_seconds)
    session.save(update_fields=['state', 'ended_at', 'inactive_minutes', 'inactive_seconds'])
    if now > session.started_at:
        TimeEntry.objects.create(
            user=request.user,
            project=session.project,
            task=session.task,
            start=session.started_at,
            end=now,
            source=TimeEntry.Source.AUTO,
            editable_until=employee_time_entry_edit_deadline(session.started_at),
            inactive_minutes=session.inactive_minutes,
            inactive_seconds=session.inactive_seconds,
            comment='Utworzone z licznika czasu.',
        )
    messages.success(request, 'Sesja pracy została zakończona i zapisana.')
    return redirect(request.POST.get('next') or reverse('dashboard'))
