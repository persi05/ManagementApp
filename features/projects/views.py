from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from features.accounts.models import UserProfile, ensure_profile, is_management, user_role
from features.accounts.permissions import management_required
from features.projects.forms import ProjectAssignmentForm, ProjectForm, ProjectLabelRateForm
from features.projects.models import ProjectAssignment, ProjectLabelRate
from features.projects.selectors import visible_projects
from features.tasks.services import ensure_default_columns


@login_required
def projects(request):
    can_view_client_rates = is_management(request.user) or user_role(request.user) == UserProfile.Role.CLIENT
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
            messages.success(request, 'Projekt zostal utworzony.')
            return redirect('projects')
    else:
        form = ProjectForm()
    page_obj = Paginator(visible_projects(request.user).order_by('name', 'id'), 50).get_page(request.GET.get('page'))
    return render(request, 'features/projects.html', {
        'projects': page_obj.object_list,
        'page_obj': page_obj,
        'form': form,
        'can_manage': is_management(request.user),
        'can_view_client_rates': can_view_client_rates,
        'default_tasks_project_id': request.user.profile.default_tasks_project_id,
    })


@login_required
@require_POST
def set_default_tasks_project(request, project_id):
    project = get_object_or_404(visible_projects(request.user), pk=project_id)
    profile = ensure_profile(request.user)
    profile.default_tasks_project = project
    profile.save(update_fields=['default_tasks_project'])
    messages.success(request, f'Projekt {project.name} będzie otwierany domyślnie w zadaniach.')
    return redirect('projects')


@login_required
def project_detail(request, project_id):
    project = get_object_or_404(visible_projects(request.user), pk=project_id)
    can_view_client_rates = is_management(request.user) or user_role(request.user) == UserProfile.Role.CLIENT
    assignment_form = ProjectAssignmentForm(project=project)
    project_form = ProjectForm(instance=project)
    label_rate_form = ProjectLabelRateForm(project=project)

    if request.method == 'POST':
        forbidden = management_required(request.user)
        if forbidden:
            return forbidden

        form_name = request.POST.get('form')
        if form_name == 'project_settings':
            project_form = ProjectForm(request.POST, instance=project)
            if project_form.is_valid():
                project = project_form.save()
                if project.client:
                    ProjectAssignment.objects.get_or_create(
                        project=project,
                        user=project.client,
                        defaults={'project_role': ProjectAssignment.ProjectRole.CLIENT},
                    )
                messages.success(request, 'Ustawienia projektu zostaly zapisane.')
                return redirect('project_detail', project_id=project.id)
        elif form_name == 'label_rate':
            rate_id = request.POST.get('rate_id')
            instance = ProjectLabelRate.objects.filter(project=project, pk=rate_id).first() if rate_id else None
            if instance is None:
                label = request.POST.get('label', '').strip().lower()
                if label:
                    instance = ProjectLabelRate.objects.filter(project=project, label=label).first()
            label_rate_form = ProjectLabelRateForm(request.POST, project=project, instance=instance)
            if label_rate_form.is_valid():
                label_rate_form.save()
                messages.success(request, 'Stawka labela zostala zapisana.')
                return redirect('project_detail', project_id=project.id)
            messages.error(request, 'Nie udalo sie zapisac stawki labela. Sprawdz label i cene.')
        else:
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
                messages.success(request, 'Uzytkownik zostal przypisany do projektu.' if created else 'Przypisanie zostalo zaktualizowane.')
                return redirect('project_detail', project_id=project.id)

    assignments = project.projectassignment_set.select_related('user', 'user__profile').order_by('project_role', 'user__last_name', 'user__username')
    return render(request, 'features/project_detail.html', {
        'project': project,
        'assignments': assignments,
        'assignment_form': assignment_form,
        'project_form': project_form,
        'label_rate_form': label_rate_form,
        'label_rates': project.label_rates.all(),
        'can_manage': is_management(request.user),
        'can_view_client_rates': can_view_client_rates,
    })


@login_required
@require_POST
def remove_project_label_rate(request, rate_id):
    forbidden = management_required(request.user)
    if forbidden:
        return forbidden

    rate = get_object_or_404(ProjectLabelRate, pk=rate_id)
    project_id = rate.project_id
    rate.delete()
    messages.success(request, 'Stawka labela zostala usunieta.')
    return redirect('project_detail', project_id=project_id)


@login_required
@require_POST
def remove_project_assignment(request, assignment_id):
    forbidden = management_required(request.user)
    if forbidden:
        return forbidden

    assignment = get_object_or_404(ProjectAssignment, pk=assignment_id)
    project_id = assignment.project_id
    assignment.delete()
    messages.success(request, 'Przypisanie zostalo usuniete.')
    return redirect('project_detail', project_id=project_id)
