from django import forms
from django.utils.html import conditional_escape, format_html, format_html_join
from django.utils.safestring import mark_safe

from features.accounts.models import UserProfile, is_management, user_role
from features.projects.models import ProjectLabelRate

from .models import BoardColumn, Task, TaskWorklog
from .services import can_edit_task_fields, can_edit_task_labels, can_move_to_column


def parse_labels(value):
    return [label.strip().lower() for label in (value or '').split(',') if label.strip()]


def format_labels(labels):
    seen = []
    for label in labels:
        if label not in seen:
            seen.append(label)
    return ', '.join(seen)


class LabelTransferWidget(forms.Widget):
    template_name = ''

    def __init__(self, available_labels=None, attrs=None):
        super().__init__(attrs)
        self.available_labels = available_labels or []

    def render(self, name, value, attrs=None, renderer=None):
        selected_labels = parse_labels(value)
        available_labels = [label for label in self.available_labels if label not in selected_labels]
        attrs = attrs or {}
        hidden = forms.HiddenInput().render(name, format_labels(selected_labels), attrs, renderer)
        selected_items = self.render_items(selected_labels, 'selected')
        available_items = self.render_items(available_labels, 'available')
        return format_html(
            '{}'
            '<div class="label-transfer" data-label-transfer>'
            '<div class="label-transfer-panel">'
            '<span>Aktualne etykiety:</span>'
            '<div class="label-transfer-box" data-label-selected>{}</div>'
            '</div>'
            '<div class="label-transfer-controls">'
            '<button type="button" class="ghost-btn tiny-btn" data-label-move="left" aria-label="Dodaj etykiety"><span>&larr;</span> Dodaj</button>'
            '<button type="button" class="ghost-btn tiny-btn" data-label-move="right" aria-label="Usuń etykiety">Usuń <span>&rarr;</span></button>'
            '</div>'
            '<div class="label-transfer-panel">'
            '<span>Dostępne etykiety:</span>'
            '<div class="label-transfer-box" data-label-available>{}</div>'
            '</div>'
            '<div class="label-transfer-new">'
            '<span>Dodaj nową etykietę:</span>'
            '<input type="text" data-label-new placeholder="Nowa etykieta">'
            '<button type="button" class="ghost-btn tiny-btn" data-label-add>Dodaj</button>'
            '</div>'
            '</div>',
            hidden,
            selected_items,
            available_items,
        )

    def render_items(self, labels, group):
        if not labels:
            return mark_safe('<button type="button" class="label-transfer-empty" disabled>Brak</button>')
        return format_html_join(
            '',
            '<button type="button" class="label-transfer-item" data-label-item data-label-group="{}" data-label-value="{}">{}</button>',
            ((group, conditional_escape(label), label) for label in labels),
        )


def setup_label_widget(form, project):
    rates = list(ProjectLabelRate.objects.filter(project=project).order_by('label'))
    form.fields['labels'].widget = LabelTransferWidget([rate.label for rate in rates])
    form.fields['labels'].label = ''
    return rates


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

        self._setup_label_suggestions()
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

    def _setup_label_suggestions(self):
        if 'labels' not in self.fields or self.project is None:
            return
        self.project_label_rates = setup_label_widget(self, self.project)

    def clean_labels(self):
        return format_labels(parse_labels(self.cleaned_data.get('labels')))


class BoardColumnForm(forms.ModelForm):
    class Meta:
        model = BoardColumn
        fields = ('name', 'is_done_column')
        labels = {
            'name': 'Nazwa kolumny',
            'is_done_column': 'Tu trafiają zadania zakończone',
        }


class BoardColumnSettingsForm(forms.ModelForm):
    class Meta:
        model = BoardColumn
        fields = (
            'name',
            'is_done_column',
            'client_can_move_to',
            'client_can_edit_tasks',
            'client_can_delete_tasks',
            'employee_can_move_to',
            'employee_can_edit_tasks',
            'employee_can_delete_tasks',
            'lead_can_move_to',
            'lead_can_edit_tasks',
            'lead_can_delete_tasks',
            'notify_client_on_task_create',
            'notify_client_on_note',
            'notify_client_on_move_to',
            'notify_assignee_on_move_to',
        )
        labels = {
            'name': 'Nazwa kolumny',
            'is_done_column': 'Tu trafiają zadania zakończone',
            'client_can_move_to': 'Klient: przenoszenie',
            'client_can_edit_tasks': 'Klient: edycja',
            'client_can_delete_tasks': 'Klient: usuwanie',
            'employee_can_move_to': 'Pracownik: przenoszenie',
            'employee_can_edit_tasks': 'Pracownik: edycja',
            'employee_can_delete_tasks': 'Pracownik: usuwanie',
            'lead_can_move_to': 'Lead: przenoszenie',
            'lead_can_edit_tasks': 'Lead: edycja',
            'lead_can_delete_tasks': 'Lead: usuwanie',
            'notify_client_on_task_create': 'Klient: nowe zadanie w tej kolumnie',
            'notify_client_on_note': 'Klient: notatka w tej kolumnie',
            'notify_client_on_move_to': 'Klient: przeniesienie tutaj',
            'notify_assignee_on_move_to': 'Pracownik: przeniesienie tutaj',
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
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].input_formats = ['%Y-%m-%d']

    def clean_hours(self):
        hours = self.cleaned_data['hours']
        if hours <= 0:
            raise forms.ValidationError('Liczba godzin musi być większa od zera.')
        return hours


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

        self._setup_label_suggestions()
        field_order = ['title', 'due_date', 'priority']
        if 'labels' in self.fields:
            field_order.append('labels')
        field_order.append('description')
        if 'assignee' in self.fields:
            field_order.append('assignee')
        field_order.append('change_note')
        self.order_fields(field_order)

    def _setup_label_suggestions(self):
        if 'labels' not in self.fields:
            return
        project = self.project or getattr(self.instance, 'project', None)
        if project is None:
            return
        self.project_label_rates = setup_label_widget(self, project)

    def clean_labels(self):
        return format_labels(parse_labels(self.cleaned_data.get('labels')))
