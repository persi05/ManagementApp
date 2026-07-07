from django import forms
from django.contrib.auth.models import User

from features.accounts.models import UserProfile

from .models import Project, ProjectAssignment


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ('name', 'description', 'client', 'status')
        labels = {
            'name': 'Nazwa',
            'description': 'Opis',
            'client': 'Klient',
            'status': 'Status',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].queryset = User.objects.filter(profile__role=UserProfile.Role.CLIENT).order_by('last_name', 'first_name', 'username')


class ProjectAssignmentForm(forms.ModelForm):
    class Meta:
        model = ProjectAssignment
        fields = ('user', 'project_role')
        labels = {
            'user': 'Użytkownik',
            'project_role': 'Rola w projekcie',
        }

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.exclude(profile__role=UserProfile.Role.MANAGEMENT).order_by('last_name', 'first_name', 'username')

    def save(self, commit=True):
        assignment = super().save(commit=False)
        if self.project:
            assignment.project = self.project
        if commit:
            assignment.save()
        return assignment

    def clean(self):
        cleaned = super().clean()
        user = cleaned.get('user')
        project_role = cleaned.get('project_role')
        if not user or not project_role:
            return cleaned

        system_role = getattr(getattr(user, 'profile', None), 'role', None)
        if project_role == ProjectAssignment.ProjectRole.CLIENT and system_role != UserProfile.Role.CLIENT:
            self.add_error('user', 'Rolę klienta w projekcie można nadać tylko użytkownikowi z rolą Klient.')
        if project_role in {ProjectAssignment.ProjectRole.EMPLOYEE, ProjectAssignment.ProjectRole.LEAD} and system_role != UserProfile.Role.EMPLOYEE:
            self.add_error('user', 'Rolę pracownika/leada w projekcie można nadać tylko użytkownikowi z rolą Pracownik.')
        return cleaned
