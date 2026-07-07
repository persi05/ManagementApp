from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from features.accounts.models import UserProfile, is_management, user_role
from features.accounts.permissions import optional_pk, worker_required
from features.projects.selectors import visible_projects
from features.tasks.forms import TaskForm, WorklogForm
from features.tasks.models import BoardColumn, Notification, TaskWorklog
from features.tasks.selectors import visible_tasks
from features.tasks.services import ensure_default_columns


@login_required
def kanban(request, project_id=None):
    projects_qs = visible_projects(request.user)
    project = get_object_or_404(projects_qs, pk=project_id) if project_id else projects_qs.first()
    if not project:
        return render(request, 'features/kanban.html', {'project': None, 'projects': projects_qs})
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
    return render(request, 'features/kanban.html', {
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
    return render(request, 'features/worklogs.html', {'worklogs': qs[:100], 'form': form, 'role': user_role(request.user)})


@login_required
@require_POST
def toggle_worklog_visibility(request, worklog_id):
    qs = TaskWorklog.objects.all() if is_management(request.user) else TaskWorklog.objects.filter(user=request.user)
    worklog = get_object_or_404(qs, pk=worklog_id)
    worklog.visible_to_client = not worklog.visible_to_client
    worklog.save(update_fields=['visible_to_client'])
    return redirect('worklogs')
