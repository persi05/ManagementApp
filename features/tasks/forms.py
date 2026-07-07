from django import forms

from features.accounts.models import UserProfile, is_management, user_role

from .models import BoardColumn, Task, TaskWorklog
from .services import can_edit_task_fields, can_edit_task_labels, project_role_for


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ('project', 'column', 'title', 'description', 'assignee', 'due_date', 'priority', 'labels')
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }
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

    def __init__(self, *args, user=None, project=None, projects_queryset=None, **kwargs):
        self.user = user
        self.project = project
        super().__init__(*args, **kwargs)

        if projects_queryset is not None:
            self.fields['project'].queryset = projects_queryset

        if project is not None and 'column' in self.fields:
            column_qs = BoardColumn.objects.filter(project=project)
            if user is not None and project_role_for(user, project) == UserProfile.Role.EMPLOYEE and not is_management(user):
                column_qs = column_qs.exclude(position__gte=3)
            self.fields['column'].queryset = column_qs
            self.fields['column'].initial = project.columns.order_by('position').first()

        if user is not None and not is_management(user):
            self.fields.pop('assignee', None)
            self.fields.pop('labels', None)

        if user is not None and user_role(user) == UserProfile.Role.CLIENT:
            self.fields.pop('column', None)

        field_order = ['project', 'title', 'due_date', 'priority']
        if 'column' in self.fields:
            field_order.append('column')
        if 'labels' in self.fields:
            field_order.append('labels')
        field_order.append('description')
        if 'assignee' in self.fields:
            field_order.append('assignee')
        self.order_fields(field_order)


class BoardColumnForm(forms.ModelForm):
    class Meta:
        model = BoardColumn
        fields = ('name',)
        labels = {'name': 'Nazwa kolumny'}


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


class TaskEditForm(forms.ModelForm):
    change_note = forms.CharField(
        label='Notatka zmiany',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    class Meta:
        model = Task
        fields = ('title', 'description', 'due_date', 'priority', 'assignee', 'labels')
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'title': 'Tytuł',
            'description': 'Opis',
            'assignee': 'Przypisany',
            'due_date': 'Termin',
            'priority': 'Priorytet',
            'labels': 'Etykiety',
        }

    def __init__(self, *args, user=None, project=None, **kwargs):
        self.user = user
        self.project = project
        super().__init__(*args, **kwargs)

        if user is not None and not is_management(user):
            self.fields.pop('assignee', None)
        if user is not None and self.instance.pk and not can_edit_task_labels(user, self.instance):
            self.fields.pop('labels', None)
        if user is not None and self.instance.pk and not can_edit_task_fields(user, self.instance):
            for field_name in ('title', 'due_date', 'priority', 'description'):
                self.fields[field_name].disabled = True
                self.fields[field_name].widget.attrs['class'] = 'readonly-field'

        field_order = ['title', 'due_date', 'priority']
        if 'labels' in self.fields:
            field_order.append('labels')
        field_order.append('description')
        if 'assignee' in self.fields:
            field_order.append('assignee')
        field_order.append('change_note')
        self.order_fields(field_order)
