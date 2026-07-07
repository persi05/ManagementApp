from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from features.accounts.models import is_management
from features.accounts.permissions import management_required
from features.projects.forms import ProjectAssignmentForm, ProjectForm
from features.projects.models import ProjectAssignment
from features.projects.selectors import visible_projects
from features.tasks.services import ensure_default_columns


@login_required
def projects(request):
    if request.method == 'POST':
        if not is_management(request.user):
            return management_required(request.user)
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
    return render(request, 'features/projects.html', {'projects': visible_projects(request.user), 'form': form, 'can_manage': is_management(request.user)})


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
    return render(request, 'features/project_detail.html', {
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
