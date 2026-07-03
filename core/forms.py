from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import HourlyRate, Project, ProjectAssignment, Task, TaskWorklog, TimeEntry, UserProfile


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=120, required=True, label='Imię')
    last_name = forms.CharField(max_length=120, required=True, label='Nazwisko')

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')


class AccountForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')
        labels = {
            'first_name': 'Imię',
            'last_name': 'Nazwisko',
            'email': 'E-mail',
        }


class UserRoleForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('role', 'is_blocked')
        labels = {
            'role': 'Rola',
            'is_blocked': 'Zablokuj konto użytkownika',
        }
        help_texts = {
            'is_blocked': 'Zablokowany użytkownik nie może korzystać z aplikacji.',
        }


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


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ('project', 'column', 'title', 'description', 'assignee', 'due_date', 'priority', 'labels')
        widgets = {'due_date': forms.DateInput(attrs={'type': 'date'})}
        labels = {
            'project': 'Projekt',
            'column': 'Kolumna',
            'title': 'Tytuł',
            'description': 'Opis',
            'assignee': 'Przypisany',
            'due_date': 'Termin',
            'priority': 'Priorytet',
            'labels': 'Etykiety',
        }


class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = ('project', 'task', 'start', 'end', 'comment')
        labels = {
            'project': 'Projekt',
            'task': 'Zadanie',
            'start': 'Rozpoczęcie pracy',
            'end': 'Zakończenie pracy',
            'comment': 'Komentarz',
        }
        help_texts = {
            'start': 'Podaj datę i godzinę rozpoczęcia pracy.',
            'end': 'Podaj datę i godzinę zakończenia pracy. Wpis czasu pracy musi mieć konkretny koniec.',
            'comment': 'Opcjonalnie opisz korektę, np. „zapomniałem uruchomić licznik”.',
        }
        widgets = {
            'start': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start')
        end = cleaned.get('end')
        if start and not end:
            self.add_error('end', 'Podaj godzinę zakończenia pracy.')
        if start and end and end <= start:
            raise forms.ValidationError('Godzina zakończenia musi być późniejsza niż rozpoczęcia.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        local_day_end = timezone.localtime(instance.start).replace(hour=23, minute=59, second=59, microsecond=999999)
        instance.editable_until = local_day_end
        if commit:
            instance.save()
        return instance


class WorklogForm(forms.ModelForm):
    class Meta:
        model = TaskWorklog
        fields = ('task', 'hours', 'date', 'comment', 'visible_to_client')
        labels = {
            'task': 'Zadanie',
            'hours': 'Godziny',
            'date': 'Data',
            'comment': 'Komentarz',
            'visible_to_client': 'Widoczne dla klienta',
        }
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}


class EmployeeProfileForm(forms.ModelForm):
    international_account = forms.BooleanField(
        label='Konto zagraniczne / IBAN',
        required=False,
        help_text='Zaznacz, jeśli numer ma format IBAN z kodem kraju, np. PL + 26 cyfr.',
    )

    class Meta:
        model = UserProfile
        fields = ('bank_account',)
        labels = {
            'bank_account': 'Numer konta bankowego',
        }
        help_texts = {
            'bank_account': 'Polski numer konta: 26 cyfr. IBAN: 2 litery kraju + 26 znaków/cyfr.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        account = (self.instance.bank_account or '').replace(' ', '') if self.instance else ''
        self.fields['international_account'].initial = len(account) == 28 and account[:2].isalpha()

    def clean(self):
        cleaned = super().clean()
        account = cleaned.get('bank_account', '')
        account = ''.join(account.split()).upper()
        if not account:
            cleaned['bank_account'] = ''
            return cleaned

        is_international = cleaned.get('international_account')
        if is_international:
            if len(account) != 28 or not account[:2].isalpha() or not account[2:].isalnum():
                self.add_error('bank_account', 'IBAN powinien mieć 28 znaków: 2 litery kraju i 26 znaków/cyfr.')
            else:
                cleaned['bank_account'] = f'{account[:2]} {account[2:]}'
            return cleaned

        if len(account) != 26 or not account.isdigit():
            self.add_error('bank_account', 'Polski numer konta powinien mieć dokładnie 26 cyfr.')
        else:
            cleaned['bank_account'] = ' '.join(account[index:index + 4] for index in range(0, len(account), 4))
        return cleaned


class HourlyRateForm(forms.ModelForm):
    class Meta:
        model = HourlyRate
        fields = ('amount', 'currency', 'valid_from', 'valid_to')
        labels = {
            'amount': 'Stawka godzinowa',
            'currency': 'Waluta',
            'valid_from': 'Obowiązuje od',
            'valid_to': 'Obowiązuje do',
        }
        help_texts = {
            'valid_to': 'Zostaw puste, jeśli stawka obowiązuje na czas nieokreślony.',
        }
        widgets = {
            'valid_from': forms.DateInput(attrs={'type': 'date'}),
            'valid_to': forms.DateInput(attrs={'type': 'date'}),
        }
