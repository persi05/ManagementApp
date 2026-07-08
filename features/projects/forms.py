from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth.models import User

from features.accounts.models import UserProfile

from .models import Project, ProjectAssignment, ProjectLabelRate


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ('name', 'description', 'client', 'status', 'client_hourly_rate', 'client_rate_currency')
        labels = {
            'name': 'Nazwa',
            'description': 'Opis',
            'client': 'Klient',
            'status': 'Status',
            'client_hourly_rate': 'Domyślna stawka klienta',
            'client_rate_currency': 'Waluta',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].queryset = User.objects.filter(profile__role=UserProfile.Role.CLIENT).order_by('last_name', 'first_name', 'username')
        self.fields['client_rate_currency'].initial = self.fields['client_rate_currency'].initial or 'PLN'
        self.fields['client_rate_currency'].required = False

    def clean_client_rate_currency(self):
        return (self.cleaned_data.get('client_rate_currency') or 'PLN').strip().upper()


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


class ProjectLabelRateForm(forms.ModelForm):
    hourly_rate = forms.CharField(label='Stawka')

    class Meta:
        model = ProjectLabelRate
        fields = ('label', 'hourly_rate', 'currency')
        labels = {
            'label': 'Label',
            'hourly_rate': 'Stawka',
            'currency': 'Waluta',
        }

    def __init__(self, *args, project=None, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)
        self.fields['currency'].initial = self.fields['currency'].initial or 'PLN'

    def clean_label(self):
        return self.cleaned_data['label'].strip().lower()

    def clean_hourly_rate(self):
        raw_value = self.cleaned_data['hourly_rate'].strip().replace(',', '.')
        try:
            value = Decimal(raw_value)
        except InvalidOperation as exc:
            raise forms.ValidationError('Podaj poprawna stawke, np. 150.00.') from exc
        if value < 0:
            raise forms.ValidationError('Stawka nie moze byc ujemna.')
        return value

    def clean_currency(self):
        return (self.cleaned_data.get('currency') or 'PLN').strip().upper()

    def save(self, commit=True):
        rate = super().save(commit=False)
        if self.project:
            rate.project = self.project
        if commit:
            rate.save()
        return rate
