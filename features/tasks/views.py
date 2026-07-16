from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Max, Sum
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from features.accounts.models import UserProfile, is_management, user_role
from features.accounts.permissions import optional_pk, worker_required
from features.documents.forms import validate_document_upload, validate_user_file_limit
from features.documents.models import DocumentAccess, DocumentItem
from features.projects.selectors import visible_projects
from features.tasks.forms import BoardColumnForm, BoardColumnSettingsForm, TaskEditForm, TaskForm, WorklogForm
from features.tasks.models import Attachment, BoardColumn, Notification, Task, TaskEditNote, TaskWorklog
from features.tasks.selectors import visible_tasks
from features.tasks.services import (
    can_delete_task,
    can_create_task_in_column,
    can_edit_task,
    can_move_task_to_column,
    can_move_to_column,
    default_permissions_for_position,
    notify_project_clients,
    notify_task_assignees,
    notify_user,
    normalize_column_positions,
    task_effective_client_rate,
    task_label_badges,
    visible_columns,
)


def classify_task_upload(uploaded_file):
    content_type = getattr(uploaded_file, 'content_type', '') or ''
    if content_type.startswith('image/'):
        return DocumentItem.Kind.IMAGE
    return DocumentItem.Kind.FILE


def grant_task_document_access(document, task):
    user_ids = set(task.project.members.values_list('id', flat=True))
    if task.project.client_id:
        user_ids.add(task.project.client_id)
    if document.owner_id:
        user_ids.add(document.owner_id)
    for user_id in user_ids:
        DocumentAccess.objects.get_or_create(item=document, user_id=user_id, defaults={'can_edit': False, 'can_manage': False})


def task_project_from_post(request, projects_qs, fallback_project):
    posted_column_id = optional_pk(request.POST.get('column'))
    if posted_column_id:
        column = BoardColumn.objects.filter(pk=posted_column_id, project__in=projects_qs).select_related('project').first()
        if column:
            return column.project

    posted_project_id = optional_pk(request.POST.get('project'))
    if posted_project_id:
        return get_object_or_404(projects_qs, pk=posted_project_id)

    return fallback_project


@login_required
def kanban(request, project_id=None):
    projects_qs = visible_projects(request.user)
    if project_id:
        project = get_object_or_404(projects_qs, pk=project_id)
    else:
        preferred_project_id = request.user.profile.default_tasks_project_id
        project = projects_qs.filter(pk=preferred_project_id).first() if preferred_project_id else None
        project = project or projects_qs.first()
    role = user_role(request.user)
    can_view_rates = is_management(request.user)
    open_task_modal = False
    if not project:
        return render(request, 'features/kanban.html', {'project': None, 'projects': projects_qs, 'can_view_rates': can_view_rates})
    if project_id is None and request.method == 'GET':
        return redirect('kanban_project', project_id=project.id)

    selected_project = project
    if request.method == 'POST':
        if request.POST.get('form') == 'board_column':
            column_form = BoardColumnForm(request.POST, project=project)
            if column_form.is_valid():
                column = column_form.save(commit=False)
                column.project = project
                max_position = project.columns.aggregate(max_position=Max('position'))['max_position']
                column.position = 0 if max_position is None else max_position + 1
                previous_column = project.columns.order_by('-position', '-id').first()
                for field_name, value in default_permissions_for_position(column.position).items():
                    setattr(column, field_name, value)
                if previous_column:
                    for field_name in BoardColumn.NOTIFICATION_FIELDS:
                        setattr(column, field_name, getattr(previous_column, field_name))
                column.save()
                messages.success(request, 'Kolumna została dodana.')
                return redirect('kanban_project', project_id=project.id)
            form = TaskForm(
                initial={'project': project},
                user=request.user,
                project=project,
                projects_queryset=projects_qs,
                fixed_project=project_id is not None,
            )
        else:
            selected_project = project if project_id is not None else task_project_from_post(request, projects_qs, project)
            form = TaskForm(
                request.POST,
                user=request.user,
                project=selected_project,
                projects_queryset=projects_qs,
                fixed_project=project_id is not None,
            )
            column_form = BoardColumnForm(project=selected_project)
            if form.is_valid():
                task = form.save(commit=False)
                task.project = selected_project
                if 'column' not in form.fields:
                    posted_column_id = optional_pk(request.POST.get('column'))
                    create_columns = visible_columns(request.user, selected_project)
                    if not is_management(request.user):
                        allowed_ids = [column.id for column in create_columns if can_create_task_in_column(request.user, selected_project, column)]
                        create_columns = create_columns.filter(id__in=allowed_ids)
                    task.column = create_columns.filter(pk=posted_column_id).first() or create_columns.order_by('position', 'id').first()
                if task.column_id is None:
                    form.add_error(None, 'Projekt nie ma jeszcze zadnej kolumny.')
                    project = selected_project
                else:
                    task.created_by = request.user
                    task.save()
                    form.save_m2m()
                    notify_task_assignees(
                        task,
                        'Nowe zadanie',
                        f'Przypisano Ci zadanie: {task.title}',
                        kind='task',
                        url=reverse('edit_task', args=[task.id]),
                        actor=request.user,
                    )
                    if task.column.notify_client_on_task_create:
                        notify_project_clients(
                            task.project,
                            'Nowe zadanie w projekcie',
                            f'Dodano zadanie: {task.title}',
                            kind='client_task',
                            url=reverse('edit_task', args=[task.id]),
                            actor=request.user,
                        )
                    messages.success(request, 'Zadanie zostało dodane.')
                    return redirect('kanban_project', project_id=task.project_id)
            open_task_modal = True
            project = selected_project
    else:
        form = TaskForm(
            initial={'project': project},
            user=request.user,
            project=project,
            projects_queryset=projects_qs,
            fixed_project=project_id is not None,
        )
        column_form = BoardColumnForm(project=project)

    columns = visible_columns(request.user, project).prefetch_related(
        'tasks__assignee',
        'tasks__assignees',
        'tasks__worklogs',
        'tasks__checklist',
        'tasks__edit_notes__user',
        'tasks__attachments__document',
        'tasks__project__label_rates',
    )
    for column in columns:
        column.can_accept_tasks = can_move_to_column(request.user, project, column)
        column.can_create_tasks = can_create_task_in_column(request.user, project, column)
        for task in column.tasks.all():
            task.can_edit = can_edit_task(request.user, task)
            task.can_move = task.can_edit and any(
                can_move_task_to_column(request.user, task, target_column)
                for target_column in columns
            )
            task.label_badges = task_label_badges(task)
            task.visible_label_badges = task.label_badges[:2]
            task.hidden_label_badges_count = max(len(task.label_badges) - len(task.visible_label_badges), 0)
            task.effective_client_rate = task_effective_client_rate(task) if can_view_rates else None

    return render(request, 'features/kanban.html', {
        'project': project,
        'projects': projects_qs,
        'columns': columns,
        'form': form,
        'column_form': column_form,
        'project_label_rates': project.label_rates.all(),
        'can_view_rates': can_view_rates,
        'open_task_modal': open_task_modal,
        'can_manage_board': True,
        'can_manage_column_settings': is_management(request.user),
        'can_move_tasks': any(column.can_accept_tasks for column in columns),
        'is_client_view': role == UserProfile.Role.CLIENT,
        'role_label': request.user.profile.get_role_display(),
        'board_task_count': sum(len(column.tasks.all()) for column in columns),
        'board_done_count': sum(len(column.tasks.all()) for column in columns if column.is_done_column),
        'available_documents': DocumentItem.visible_to(request.user).filter(is_archived=False).exclude(kind=DocumentItem.Kind.FOLDER).order_by('kind', 'name')[:120],
    })


@login_required
@require_POST
def move_task(request, task_id):
    task = get_object_or_404(visible_tasks(request.user), pk=task_id)
    column = get_object_or_404(BoardColumn, pk=request.POST.get('column'), project=task.project)
    if not can_move_task_to_column(request.user, task, column):
        return HttpResponseForbidden('Brak uprawnień do zmiany statusu zadania.')
    previous_column_id = task.column_id
    task.column = column
    task.save(update_fields=['column', 'updated_at'])
    if previous_column_id != column.id and column.notify_assignee_on_move_to:
        notify_task_assignees(
            task,
            'Zmieniono status zadania',
            f'{task.title} jest teraz w kolumnie {column.name}.',
            kind='task',
            url=reverse('edit_task', args=[task.id]),
            actor=request.user,
        )
    if previous_column_id != column.id and column.notify_client_on_move_to:
        notify_project_clients(
            task.project,
            'Zmieniono status zadania',
            f'{task.title} jest teraz w kolumnie {column.name}.',
            kind='client_task',
            url=reverse('kanban_project', args=[task.project_id]),
            actor=request.user,
        )
    return JsonResponse({'ok': True, 'column': column.name})


@login_required
@require_POST
def update_task_card(request, task_id):
    task = get_object_or_404(visible_tasks(request.user), pk=task_id)
    if not can_edit_task(request.user, task):
        return HttpResponseForbidden('Brak uprawnien do zmiany karty zadania.')

    action = request.POST.get('action')
    if action == 'toggle_star':
        task.is_starred = not task.is_starred
        task.save(update_fields=['is_starred', 'updated_at'])
    elif action == 'set_color':
        color = request.POST.get('color', Task.CardColor.DEFAULT)
        if color not in Task.CardColor.values:
            return JsonResponse({'ok': False, 'error': 'Nieprawidlowy kolor.'}, status=400)
        task.card_color = color
        task.save(update_fields=['card_color', 'updated_at'])
    else:
        return JsonResponse({'ok': False, 'error': 'Nieprawidlowa akcja.'}, status=400)

    return JsonResponse({
        'ok': True,
        'is_starred': task.is_starred,
        'card_color': task.card_color,
    })


@login_required
def update_column(request, column_id):
    if not is_management(request.user):
        return HttpResponseForbidden('Brak uprawnień do edycji ustawień kolumny.')

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
    column = get_object_or_404(BoardColumn, pk=column_id, project__in=visible_projects(request.user))
    project = column.project
    if project.columns.count() <= 1:
        messages.error(request, 'Projekt musi miec przynajmniej jedna kolumne.')
        return redirect('kanban_project', project_id=project.id)
    if column.tasks.exists():
        messages.error(request, 'Nie można usunąć kolumny, która ma zadania.')
        return redirect('kanban_project', project_id=project.id)

    column.delete()
    normalize_column_positions(project)
    messages.success(request, 'Kolumna została usunięta.')
    return redirect('kanban_project', project_id=project.id)


@login_required
@require_POST
def add_task_note(request, task_id):
    task = get_object_or_404(visible_tasks(request.user), pk=task_id)
    if not can_edit_task(request.user, task):
        return HttpResponseForbidden('Brak uprawnień do dodania notatki.')

    note = (request.POST.get('content') or '').strip()
    if note:
        TaskEditNote.objects.create(task=task, user=request.user, content=note)
        notify_task_assignees(
            task,
            'Nowa notatka do zadania',
            f'Dodano notatke do zadania: {task.title}',
            kind='task_note',
            url=reverse('edit_task', args=[task.id]),
            actor=request.user,
        )
        if task.column.notify_client_on_note:
            notify_project_clients(
                task.project,
                'Nowa notatka do zadania',
                f'Dodano notatke do zadania: {task.title}',
                kind='client_note',
                url=reverse('edit_task', args=[task.id]),
                actor=request.user,
            )
        messages.success(request, 'Notatka została dodana.')
    else:
        messages.error(request, 'Wpisz tresc notatki.')
    return redirect('kanban_project', project_id=task.project_id)


@login_required
@require_POST
def add_task_attachment(request, task_id):
    task = get_object_or_404(visible_tasks(request.user), pk=task_id)
    if not can_edit_task(request.user, task):
        return HttpResponseForbidden('Brak uprawnień do dodania załącznika.')

    uploaded = request.FILES.get('file')
    name = (request.POST.get('name') or '').strip()
    if uploaded:
        try:
            validate_document_upload(uploaded)
            validate_user_file_limit(request.user)
        except ValidationError as error:
            for message in error.messages:
                messages.error(request, message)
            return redirect('kanban_project', project_id=task.project_id)
        document = DocumentItem.objects.create(
            owner=request.user,
            name=name or uploaded.name,
            kind=classify_task_upload(uploaded),
            file=uploaded,
            project=task.project,
        )
        grant_task_document_access(document, task)
        Attachment.objects.create(task=task, name=document.name, document=document)
        messages.success(request, 'Zalacznik zostal dodany.')
    else:
        messages.error(request, 'Wybierz plik do zalaczenia.')
    return redirect('kanban_project', project_id=task.project_id)


@login_required
@require_POST
def link_task_document(request, task_id):
    task = get_object_or_404(visible_tasks(request.user), pk=task_id)
    if not can_edit_task(request.user, task):
        return HttpResponseForbidden('Brak uprawnień do powiązania dokumentu.')

    document = get_object_or_404(
        DocumentItem.visible_to(request.user).exclude(kind=DocumentItem.Kind.FOLDER),
        pk=request.POST.get('document'),
    )
    Attachment.objects.get_or_create(
        task=task,
        document=document,
        defaults={'name': document.name},
    )
    grant_task_document_access(document, task)
    messages.success(request, 'Dokument zostal powiazany z zadaniem.')
    return redirect('kanban_project', project_id=task.project_id)


@login_required
def edit_task(request, task_id):
    task = get_object_or_404(visible_tasks(request.user), pk=task_id)
    if not can_edit_task(request.user, task):
        return HttpResponseForbidden('Brak uprawnień do edycji zadania.')

    if request.method == 'POST':
        previous_assignee_ids = set(task.assignees.values_list('id', flat=True))
        if not previous_assignee_ids and task.assignee_id:
            previous_assignee_ids.add(task.assignee_id)
        form = TaskEditForm(request.POST, instance=task, user=request.user, project=task.project)
        if form.is_valid():
            updated_task = form.save()
            current_assignee_ids = set(updated_task.assignees.values_list('id', flat=True))
            if not current_assignee_ids and updated_task.assignee_id:
                current_assignee_ids.add(updated_task.assignee_id)
            new_assignee_ids = current_assignee_ids - previous_assignee_ids
            if new_assignee_ids:
                notify_task_assignees(
                    updated_task,
                    'Nowe przypisanie',
                    f'Przypisano Ci zadanie: {updated_task.title}',
                    kind='task',
                    url=reverse('edit_task', args=[updated_task.id]),
                    actor=request.user,
                    exclude_ids=current_assignee_ids - new_assignee_ids,
                )
            note = form.cleaned_data.get('change_note', '').strip()
            if note:
                TaskEditNote.objects.create(task=updated_task, user=request.user, content=note)
                notify_task_assignees(
                    updated_task,
                    'Nowa notatka do zadania',
                    f'Dodano notatke do zadania: {updated_task.title}',
                    kind='task_note',
                    url=reverse('edit_task', args=[updated_task.id]),
                    actor=request.user,
                )
                if updated_task.column.notify_client_on_note:
                    notify_project_clients(
                        updated_task.project,
                        'Nowa notatka do zadania',
                        f'Dodano notatke do zadania: {updated_task.title}',
                        kind='client_note',
                        url=reverse('edit_task', args=[updated_task.id]),
                        actor=request.user,
                    )
            messages.success(request, 'Zadanie zostało zapisane.')
            return redirect('edit_task', task_id=task.id)
    else:
        form = TaskEditForm(instance=task, user=request.user, project=task.project)

    history = task.edit_notes.select_related('user')
    return render(request, 'features/task_edit.html', {
        'task': task,
        'form': form,
        'project_label_rates': getattr(form, 'project_label_rates', []),
        'can_view_rates': is_management(request.user),
        'history': history,
        'can_delete_task': can_delete_task(request.user, task),
    })


@login_required
@require_POST
def delete_task(request, task_id):
    task = get_object_or_404(visible_tasks(request.user), pk=task_id)
    if not can_delete_task(request.user, task):
        return HttpResponseForbidden('Brak uprawnień do usunięcia zadania.')

    project_id = task.project_id
    task.delete()
    messages.success(request, 'Zadanie zostało usunięte.')
    return redirect('kanban_project', project_id=project_id)


@login_required
def worklogs(request):
    if request.method == 'POST':
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
        item.can_toggle_visibility = is_management(request.user) or item.user_id == request.user.id
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
        return HttpResponseForbidden('Nie można już edytować tego czasu zadania.')

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
    requested_visibility = request.POST.get('visible_to_client')
    if requested_visibility is None:
        worklog.visible_to_client = not worklog.visible_to_client
    else:
        worklog.visible_to_client = requested_visibility in {'1', 'true', 'on', 'yes'}
    worklog.save(update_fields=['visible_to_client'])
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'visible_to_client': worklog.visible_to_client})
    return redirect('worklogs')


@login_required
def notifications(request):
    notifications_qs = request.user.notifications.all()
    paginator = Paginator(notifications_qs, settings.NOTIFICATIONS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page'))
    unread_count = request.user.notifications.filter(is_read=False).count()
    return render(request, 'features/notifications.html', {
        'page_obj': page_obj,
        'notifications': page_obj.object_list,
        'total_count': paginator.count,
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
