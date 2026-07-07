from django import forms

from features.accounts.models import UserProfile, is_management, user_role

from .models import BoardColumn, Task, TaskWorklog
from .services import can_edit_task_fields, can_edit_task_labels, can_move_to_column


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

    def __init__(self, *args, user=None, project=None, projects_queryset=None, fixed_project=False, **kwargs):
        self.user = user
        self.project = project
        self.fixed_project = fixed_project
        super().__init__(*args, **kwargs)

        if projects_queryset is not None:
            self.fields['project'].queryset = projects_queryset

        if fixed_project:
            self.fields.pop('project', None)

        if project is not None and 'column' in self.fields:
            column_qs = BoardColumn.objects.filter(project=project)
            if user is not None and not is_management(user):
                allowed_ids = [column.id for column in column_qs if can_move_to_column(user, project, column)]
                column_qs = column_qs.filter(id__in=allowed_ids)
            self.fields['column'].queryset = column_qs
            self.fields['column'].initial = column_qs.order_by('position', 'id').first()

        if user is not None and not is_management(user):
            self.fields.pop('assignee', None)
            self.fields.pop('labels', None)

        if user is not None and user_role(user) == UserProfile.Role.CLIENT:
            self.fields.pop('column', None)

        field_order = ['title', 'due_date', 'priority']
        if 'project' in self.fields:
            field_order.insert(0, 'project')
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


class BoardColumnSettingsForm(forms.ModelForm):
    class Meta:
        model = BoardColumn
        fields = (
            'name',
            'client_can_move_to',
            'client_can_edit_tasks',
            'client_can_delete_tasks',
            'employee_can_move_to',
            'employee_can_edit_tasks',
            'employee_can_delete_tasks',
            'lead_can_move_to',
            'lead_can_edit_tasks',
            'lead_can_delete_tasks',
        )
        labels = {
            'name': 'Nazwa kolumny',
            'client_can_move_to': 'Klient: przenoszenie',
            'client_can_edit_tasks': 'Klient: edycja',
            'client_can_delete_tasks': 'Klient: usuwanie',
            'employee_can_move_to': 'Pracownik: przenoszenie',
            'employee_can_edit_tasks': 'Pracownik: edycja',
            'employee_can_delete_tasks': 'Pracownik: usuwanie',
            'lead_can_move_to': 'Lead: przenoszenie',
            'lead_can_edit_tasks': 'Lead: edycja',
            'lead_can_delete_tasks': 'Lead: usuwanie',
        }


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
