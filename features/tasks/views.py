from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Max, Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from features.accounts.models import UserProfile, is_management, user_role
from features.accounts.permissions import optional_pk, worker_required
from features.projects.selectors import visible_projects
from features.tasks.forms import BoardColumnForm, BoardColumnSettingsForm, TaskEditForm, TaskForm, WorklogForm
from features.tasks.models import BoardColumn, Notification, TaskEditNote, TaskWorklog
from features.tasks.selectors import visible_tasks
from features.tasks.services import (
    can_delete_task,
    can_edit_task,
    can_move_task_to_column,
    can_move_to_column,
    default_permissions_for_position,
    is_first_project_column,
    is_last_project_column,
    notify_project_clients,
    notify_user,
    normalize_column_positions,
)


@login_required
def kanban(request, project_id=None):
    projects_qs = visible_projects(request.user)
    project = get_object_or_404(projects_qs, pk=project_id) if project_id else projects_qs.first()
    if not project:
        return render(request, 'features/kanban.html', {'project': None, 'projects': projects_qs})

    selected_project = project
    if request.method == 'POST':
        if request.POST.get('form') == 'board_column':
            if not is_management(request.user):
                return HttpResponseForbidden('Brak uprawnien do dodania kolumny.')
            column_form = BoardColumnForm(request.POST)
            if column_form.is_valid():
                column = column_form.save(commit=False)
                column.project = project
                max_position = project.columns.aggregate(max_position=Max('position'))['max_position']
                column.position = 0 if max_position is None else max_position + 1
                previous_column = project.columns.order_by('-position', '-id').first()
                if previous_column:
                    for field_name in BoardColumn.PERMISSION_FIELDS:
                        setattr(column, field_name, getattr(previous_column, field_name))
                else:
                    for field_name, value in default_permissions_for_position(0).items():
                        setattr(column, field_name, value)
                column.save()
                messages.success(request, 'Kolumna zostala dodana.')
                return redirect('kanban_project', project_id=project.id)
            form = TaskForm(
                initial={'project': project},
                user=request.user,
                project=project,
                projects_queryset=projects_qs,
                fixed_project=project_id is not None,
            )
        else:
            selected_project_id = project.id if project_id is not None else optional_pk(request.POST.get('project')) or project.id
            selected_project = get_object_or_404(projects_qs, pk=selected_project_id)
            form = TaskForm(
                request.POST,
                user=request.user,
                project=selected_project,
                projects_queryset=projects_qs,
                fixed_project=project_id is not None,
            )
            column_form = BoardColumnForm()
            if 'assignee' in form.fields:
                form.fields['assignee'].queryset = User.objects.filter(
                    projectassignment__project_id=selected_project.id,
                    profile__role=UserProfile.Role.EMPLOYEE,
                ).distinct()
            if form.is_valid():
                task = form.save(commit=False)
                task.project = selected_project
                if 'column' not in form.fields:
                    task.column = selected_project.columns.order_by('position', 'id').first()
                if task.column_id is None:
                    form.add_error(None, 'Projekt nie ma jeszcze zadnej kolumny.')
                    project = selected_project
                else:
                    task.created_by = request.user
                    task.save()
                    notify_user(
                        task.assignee,
                        'Nowe zadanie',
                        f'Przypisano Ci zadanie: {task.title}',
                        kind='task',
                        url=reverse('edit_task', args=[task.id]),
                        actor=request.user,
                    )
                    if is_first_project_column(task):
                        notify_project_clients(
                            task.project,
                            'Nowe zadanie w projekcie',
                            f'Dodano zadanie: {task.title}',
                            kind='client_task',
                            url=reverse('edit_task', args=[task.id]),
                            actor=request.user,
                        )
                    messages.success(request, 'Zadanie zostalo dodane.')
                    return redirect('kanban_project', project_id=task.project_id)
            project = selected_project
    else:
        form = TaskForm(
            initial={'project': project},
            user=request.user,
            project=project,
            projects_queryset=projects_qs,
            fixed_project=project_id is not None,
        )
        column_form = BoardColumnForm()
        if 'assignee' in form.fields:
            form.fields['assignee'].queryset = User.objects.filter(
                projectassignment__project=project,
                profile__role=UserProfile.Role.EMPLOYEE,
            ).distinct()

    columns = project.columns.prefetch_related('tasks__assignee', 'tasks__worklogs', 'tasks__checklist')
    for column in columns:
        column.can_accept_tasks = can_move_to_column(request.user, project, column)
        for task in column.tasks.all():
            task.can_edit = can_edit_task(request.user, task)

    return render(request, 'features/kanban.html', {
        'project': project,
        'projects': projects_qs,
        'columns': columns,
        'form': form,
        'column_form': column_form,
        'can_manage_board': is_management(request.user),
        'can_move_tasks': any(column.can_accept_tasks for column in columns),
        'is_client_view': user_role(request.user) == UserProfile.Role.CLIENT,
    })


@login_required
@require_POST
def move_task(request, task_id):
    task = get_object_or_404(visible_tasks(request.user), pk=task_id)
    column = get_object_or_404(BoardColumn, pk=request.POST.get('column'), project=task.project)
    if not can_move_task_to_column(request.user, task, column):
        return HttpResponseForbidden('Brak uprawnien do zmiany statusu zadania.')
    previous_column_id = task.column_id
    task.column = column
    task.save(update_fields=['column', 'updated_at'])
    notify_user(
        task.assignee,
        'Zmieniono status zadania',
        f'{task.title} jest teraz w kolumnie {column.name}.',
        kind='task',
        url=reverse('edit_task', args=[task.id]),
        actor=request.user,
    )
    if previous_column_id != column.id and is_last_project_column(task.project, column):
        notify_project_clients(
            task.project,
            'Zadanie zakończone',
            f'Zadanie jest gotowe: {task.title}',
            kind='client_done',
            url=reverse('kanban_project', args=[task.project_id]),
            actor=request.user,
        )
    return JsonResponse({'ok': True, 'column': column.name})


def update_column(request, column_id):
    if not is_management(request.user):
        return HttpResponseForbidden('Brak uprawnien do edycji kolumny.')

    column = get_object_or_404(BoardColumn, pk=column_id, project__in=visible_projects(request.user))
    if request.method == 'POST':
        form = BoardColumnSettingsForm(request.POST, instance=column)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ustawienia kolumny zostaly zapisane.')
            return redirect('kanban_project', project_id=column.project_id)
        messages.error(request, 'Nie udalo sie zapisac ustawien kolumny.')
    else:
        form = BoardColumnSettingsForm(instance=column)

    return render(request, 'features/column_settings.html', {
        'column': column,
        'project': column.project,
        'form': form,
        'can_delete_column': column.project.columns.count() > 1 and not column.tasks.exists(),
    })


@login_required
@require_POST
def delete_column(request, column_id):
    if not is_management(request.user):
        return HttpResponseForbidden('Brak uprawnien do usuniecia kolumny.')

    column = get_object_or_404(BoardColumn, pk=column_id, project__in=visible_projects(request.user))
    project = column.project
    if project.columns.count() <= 1:
        messages.error(request, 'Projekt musi miec przynajmniej jedna kolumne.')
        return redirect('kanban_project', project_id=project.id)
    if column.tasks.exists():
        messages.error(request, 'Nie mozna usunac kolumny, ktora ma zadania.')
        return redirect('kanban_project', project_id=project.id)

    column.delete()
    normalize_column_positions(project)
    messages.success(request, 'Kolumna zostala usunieta.')
    return redirect('kanban_project', project_id=project.id)


@login_required
def edit_task(request, task_id):
    task = get_object_or_404(visible_tasks(request.user), pk=task_id)
    if not can_edit_task(request.user, task):
        return HttpResponseForbidden('Brak uprawnien do edycji zadania.')

    if request.method == 'POST':
        previous_assignee_id = task.assignee_id
        form = TaskEditForm(request.POST, instance=task, user=request.user, project=task.project)
        if form.is_valid():
            updated_task = form.save()
            if updated_task.assignee_id and updated_task.assignee_id != previous_assignee_id:
                notify_user(
                    updated_task.assignee,
                    'Nowe przypisanie',
                    f'Przypisano Ci zadanie: {updated_task.title}',
                    kind='task',
                    url=reverse('edit_task', args=[updated_task.id]),
                    actor=request.user,
                )
            note = form.cleaned_data.get('change_note', '').strip()
            if note:
                TaskEditNote.objects.create(task=updated_task, user=request.user, content=note)
                notify_user(
                    updated_task.assignee,
                    'Nowa notatka do zadania',
                    f'Dodano notatke do zadania: {updated_task.title}',
                    kind='task_note',
                    url=reverse('edit_task', args=[updated_task.id]),
                    actor=request.user,
                )
                if is_first_project_column(updated_task):
                    notify_project_clients(
                        updated_task.project,
                        'Nowa notatka do zadania',
                        f'Dodano notatke do zadania: {updated_task.title}',
                        kind='client_note',
                        url=reverse('edit_task', args=[updated_task.id]),
                        actor=request.user,
                    )
            messages.success(request, 'Zadanie zostalo zapisane.')
            return redirect('kanban_project', project_id=task.project_id)
    else:
        form = TaskEditForm(instance=task, user=request.user, project=task.project)

    history = task.edit_notes.select_related('user')
    return render(request, 'features/task_edit.html', {
        'task': task,
        'form': form,
        'history': history,
        'can_delete_task': can_delete_task(request.user, task),
    })


@login_required
@require_POST
def delete_task(request, task_id):
    task = get_object_or_404(visible_tasks(request.user), pk=task_id)
    if not can_delete_task(request.user, task):
        return HttpResponseForbidden('Brak uprawnien do usuniecia zadania.')

    project_id = task.project_id
    task.delete()
    messages.success(request, 'Zadanie zostalo usuniete.')
    return redirect('kanban_project', project_id=project_id)


@login_required
def worklogs(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    projects_qs = visible_projects(request.user)
    selected_project_id = optional_pk(request.POST.get('project') or request.GET.get('project'))
    selected_project = get_object_or_404(projects_qs, pk=selected_project_id) if selected_project_id else projects_qs.first()
    task_qs = visible_tasks(request.user)
    if selected_project:
        task_qs = task_qs.filter(project=selected_project)
    else:
        task_qs = task_qs.none()

    if request.method == 'POST':
        form = WorklogForm(request.POST)
        form.fields['task'].queryset = task_qs
        if form.is_valid():
            worklog = form.save(commit=False)
            worklog.user = request.user
            worklog.save()
            messages.success(request, 'Worklog zostal dodany.')
            return redirect(f"{reverse('worklogs')}?project={worklog.task.project_id}")
    else:
        form = WorklogForm()
        form.fields['task'].queryset = task_qs

    qs = TaskWorklog.objects.select_related('task', 'task__project', 'user')
    if is_management(request.user):
        pass
    elif user_role(request.user) == UserProfile.Role.CLIENT:
        qs = qs.filter(task__project__in=visible_projects(request.user), visible_to_client=True)
    else:
        qs = qs.filter(user=request.user)
    if selected_project:
        qs = qs.filter(task__project=selected_project)
    else:
        qs = qs.none()
    total_hours = qs.aggregate(total=Sum('hours'))['total'] or 0
    worklog_items = list(qs[:100])
    for item in worklog_items:
        item.can_edit = item.can_be_edited_by(request.user)
    return render(request, 'features/worklogs.html', {
        'worklogs': worklog_items,
        'form': form,
        'role': user_role(request.user),
        'projects': projects_qs,
        'selected_project': selected_project,
        'total_hours': total_hours,
    })


@login_required
def edit_worklog(request, worklog_id):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    qs = TaskWorklog.objects.select_related('task', 'task__project', 'user')
    if is_management(request.user):
        pass
    else:
        qs = qs.filter(user=request.user)
    worklog = get_object_or_404(qs, pk=worklog_id)
    if not worklog.can_be_edited_by(request.user):
        return HttpResponseForbidden('Nie mozna juz edytowac tego czasu zadania.')

    if request.method == 'POST':
        form = WorklogForm(request.POST, instance=worklog)
        form.fields['task'].queryset = visible_tasks(request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Czas zadania zostal zaktualizowany.')
            return redirect('worklogs')
    else:
        form = WorklogForm(instance=worklog)
        form.fields['task'].queryset = visible_tasks(request.user)

    return render(request, 'features/worklog_edit.html', {'worklog': worklog, 'form': form})


@login_required
@require_POST
def toggle_worklog_visibility(request, worklog_id):
    qs = TaskWorklog.objects.all() if is_management(request.user) else TaskWorklog.objects.filter(user=request.user)
    worklog = get_object_or_404(qs, pk=worklog_id)
    if not worklog.can_be_edited_by(request.user):
        return HttpResponseForbidden('Nie mozna juz edytowac tego czasu zadania.')
    worklog.visible_to_client = not worklog.visible_to_client
    worklog.save(update_fields=['visible_to_client'])
    return redirect('worklogs')


@login_required
def notifications(request):
    items = request.user.notifications.all()[:100]
    unread_count = request.user.notifications.filter(is_read=False).count()
    return render(request, 'features/notifications.html', {
        'notifications': items,
        'unread_count': unread_count,
    })


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    next_url = request.POST.get('next') or notification.url or reverse('notifications')
    return redirect(next_url)


@login_required
@require_POST
def mark_all_notifications_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect(request.POST.get('next') or 'notifications')
