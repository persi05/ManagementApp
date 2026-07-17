from django import forms
from django.utils.html import conditional_escape, format_html, format_html_join
from django.utils.safestring import mark_safe

from features.accounts.models import UserProfile, is_management, user_role
from features.projects.models import ProjectLabelRate

from .models import BoardColumn, Task, TaskWorklog
from .services import can_create_task_in_column, can_edit_task_fields


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
            '<div class="label-transfer-panel label-transfer-selected-panel">'
            '<span>Wybrane etykiety</span>'
            '<div class="label-transfer-box" data-label-selected>{}</div>'
            '</div>'
            '<div class="label-transfer-controls" aria-label="Przenoszenie etykiet">'
            '<button type="button" class="ghost-btn tiny-btn" data-label-move="left" aria-label="Dodaj etykiety"><span>&larr;</span> Dodaj</button>'
            '<button type="button" class="ghost-btn tiny-btn" data-label-move="right" aria-label="Usuń etykiety">Usuń <span>&rarr;</span></button>'
            '</div>'
            '<div class="label-transfer-panel label-transfer-available-panel">'
            '<span>Dostępne etykiety</span>'
            '<div class="label-transfer-box" data-label-available>{}</div>'
            '</div>'
            '<div class="label-transfer-new">'
            '<span>Dodaj własną etykietę</span>'
            '<div class="label-transfer-new-row">'
            '<input type="text" data-label-new placeholder="Nazwa nowej etykiety">'
            '<button type="button" class="ghost-btn tiny-btn" data-label-add>Dodaj etykietę</button>'
            '</div>'
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


class AssigneeTransferWidget(forms.SelectMultiple):
    def render(self, name, value, attrs=None, renderer=None):
        selected_values = {str(getattr(item, 'pk', item)) for item in (value or [])}
        attrs = attrs or {}
        attrs['data-assignee-source'] = ''
        attrs['style'] = 'display:none'
        choices = list(self.choices)
        picker_options = ['<option value="">Wybierz osobę</option>']
        selected_items = []
        for option_value, option_label in choices:
            option_value = str(option_value)
            option_label = str(option_label)
            if option_value in selected_values:
                selected_items.append((option_value, option_label))
            else:
                picker_options.append(format_html('<option value="{}">{}</option>', option_value, option_label))
        self.choices = choices
        select = super().render(name, value, attrs, renderer)
        return format_html(
            '{}'
            '<div class="assignee-picker" data-assignee-picker>'
            '<div class="assignee-picker-row">'
            '<select data-assignee-picker-select>{}</select>'
            '<button type="button" class="ghost-btn tiny-btn assignee-picker-add" data-assignee-add aria-label="Dodaj osobę">+</button>'
            '</div>'
            '<span>Przypisane osoby:</span>'
            '<div class="assignee-picker-list" data-assignee-selected>{}</div>'
            '</div>',
            mark_safe(select),
            mark_safe(''.join(str(option) for option in picker_options)),
            self.render_items(selected_items),
        )

    def render_items(self, users):
        if not users:
            return mark_safe('<p class="assignee-picker-empty" data-assignee-empty>Brak przypisanych osób.</p>')
        return format_html_join(
            '',
            '<span class="assignee-picker-item" data-assignee-item data-assignee-value="{}"><span>{}</span><button type="button" class="ghost-btn tiny-btn" data-assignee-remove aria-label="Usuń osobę">-</button></span>',
            ((value, label) for value, label in users),
        )


def setup_label_widget(form, project):
    rates = list(ProjectLabelRate.objects.filter(project=project).order_by('label'))
    form.fields['labels'].widget = LabelTransferWidget([rate.label for rate in rates])
    form.fields['labels'].label = ''
    return rates


def can_manage_task_labels(user, project):
    if user is None or project is None:
        return False
    return user.is_authenticated


def normalize_assignee_data(args):
    if not args:
        return args
    data = args[0]
    if not hasattr(data, 'copy') or 'assignees' in data or 'assignee' not in data:
        return args
    mutable_data = data.copy()
    assignee = data.get('assignee')
    if assignee:
        mutable_data.setlist('assignees', [assignee])
    return (mutable_data, *args[1:])


def assignable_users_queryset(project):
    return project.members.filter(is_active=True).exclude(profile__role=UserProfile.Role.CLIENT).order_by('first_name', 'last_name', 'username')


def setup_assignee_picker(field, project):
    field.queryset = assignable_users_queryset(project)
    widget = AssigneeTransferWidget()
    widget.choices = field.choices
    field.widget = widget


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ('project', 'column', 'title', 'description', 'assignees', 'due_date', 'priority', 'labels')
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'project': 'Projekt',
            'column': 'Kolumna',
            'title': 'Tytuł',
            'description': 'Opis',
            'assignees': 'Przypisani',
            'due_date': 'Termin',
            'priority': 'Priorytet',
            'labels': 'Etykiety',
        }

    def __init__(self, *args, user=None, project=None, projects_queryset=None, fixed_project=False, **kwargs):
        args = normalize_assignee_data(args)
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
                allowed_ids = [column.id for column in column_qs if can_create_task_in_column(user, project, column)]
                column_qs = column_qs.filter(id__in=allowed_ids)
            self.fields['column'].queryset = column_qs
            self.fields['column'].initial = column_qs.order_by('position', 'id').first()
            if fixed_project:
                self.fields['column'].widget = forms.HiddenInput()

        if user is not None and not is_management(user):
            self.fields.pop('assignees', None)

        if user is not None and not can_manage_task_labels(user, project):
            self.fields.pop('labels', None)

        if user is not None and user_role(user) == UserProfile.Role.CLIENT:
            self.fields.pop('column', None)

        for field_name, field in self.fields.items():
            field.widget.attrs['data-task-field'] = field_name

        self._setup_label_suggestions()
        field_order = ['title', 'due_date', 'priority']
        if 'project' in self.fields:
            field_order.insert(0, 'project')
        if 'column' in self.fields:
            field_order.append('column')
        if 'labels' in self.fields:
            field_order.append('labels')
        field_order.append('description')
        if 'assignees' in self.fields:
            field_order.append('assignees')
        self.order_fields(field_order)
        self._setup_assignee_field()

    def _setup_label_suggestions(self):
        if 'labels' not in self.fields or self.project is None:
            return
        self.project_label_rates = setup_label_widget(self, self.project)

    def clean_labels(self):
        return format_labels(parse_labels(self.cleaned_data.get('labels')))

    def _setup_assignee_field(self):
        if 'assignees' not in self.fields or self.project is None:
            return
        setup_assignee_picker(self.fields['assignees'], self.project)

    def save(self, commit=True):
        selected_assignees = list(self.cleaned_data.get('assignees') or [])
        task = super().save(commit=False)
        task.assignee = selected_assignees[0] if selected_assignees else None
        if commit:
            task.save()
            self.save_m2m()
            task.assignees.set(selected_assignees)
        return task


class DoneColumnValidationMixin:
    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        instance_project = self.instance.project if getattr(self.instance, 'project_id', None) else None
        self.column_project = project or instance_project

    def clean_is_done_column(self):
        is_done_column = self.cleaned_data.get('is_done_column', False)
        if not is_done_column or self.column_project is None:
            return is_done_column
        existing = BoardColumn.objects.filter(project=self.column_project, is_done_column=True)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError('Tylko jedna kolumna w projekcie może być oznaczona jako zakończona.')
        return is_done_column


class BoardColumnForm(DoneColumnValidationMixin, forms.ModelForm):
    class Meta:
        model = BoardColumn
        fields = ('name', 'is_done_column')
        labels = {
            'name': 'Nazwa kolumny',
            'is_done_column': 'Tu trafiają zadania zakończone',
        }


class BoardColumnSettingsForm(DoneColumnValidationMixin, forms.ModelForm):
    class Meta:
        model = BoardColumn
        fields = (
            'name',
            'is_done_column',
            'client_can_view_column',
            'client_can_create_tasks',
            'client_can_move_to',
            'client_can_edit_tasks',
            'client_can_delete_tasks',
            'employee_can_view_column',
            'employee_can_create_tasks',
            'employee_can_move_to',
            'employee_can_edit_tasks',
            'employee_can_delete_tasks',
            'lead_can_view_column',
            'lead_can_create_tasks',
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
            'client_can_view_column': 'Klient: widoczność kolumny',
            'client_can_create_tasks': 'Klient: tworzenie zadań',
            'client_can_move_to': 'Klient: przenoszenie',
            'client_can_edit_tasks': 'Klient: edycja',
            'client_can_delete_tasks': 'Klient: usuwanie',
            'employee_can_view_column': 'Pracownik: widoczność kolumny',
            'employee_can_create_tasks': 'Pracownik: tworzenie zadań',
            'employee_can_move_to': 'Pracownik: przenoszenie',
            'employee_can_edit_tasks': 'Pracownik: edycja',
            'employee_can_delete_tasks': 'Pracownik: usuwanie',
            'lead_can_view_column': 'Lead: widoczność kolumny',
            'lead_can_create_tasks': 'Lead: tworzenie zadań',
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
        fields = ('title', 'description', 'due_date', 'priority', 'assignees', 'labels')
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'title': 'Tytuł',
            'description': 'Opis',
            'assignees': 'Przypisani',
            'due_date': 'Termin',
            'priority': 'Priorytet',
            'labels': 'Etykiety',
        }

    def __init__(self, *args, user=None, project=None, **kwargs):
        args = normalize_assignee_data(args)
        self.user = user
        self.project = project
        super().__init__(*args, **kwargs)

        if user is not None and not is_management(user):
            self.fields.pop('assignees', None)
        task_project = self.project or getattr(self.instance, 'project', None)
        if user is not None and not can_manage_task_labels(user, task_project):
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
        if 'assignees' in self.fields:
            field_order.append('assignees')
        field_order.append('change_note')
        self.order_fields(field_order)
        self._setup_assignee_field()

    def _setup_label_suggestions(self):
        if 'labels' not in self.fields:
            return
        project = self.project or getattr(self.instance, 'project', None)
        if project is None:
            return
        self.project_label_rates = setup_label_widget(self, project)

    def clean_labels(self):
        return format_labels(parse_labels(self.cleaned_data.get('labels')))

    def _setup_assignee_field(self):
        if 'assignees' not in self.fields:
            return
        project = self.project or getattr(self.instance, 'project', None)
        if project is None:
            return
        setup_assignee_picker(self.fields['assignees'], project)

    def save(self, commit=True):
        selected_assignees = list(self.cleaned_data.get('assignees') or [])
        task = super().save(commit=False)
        task.assignee = selected_assignees[0] if selected_assignees else None
        if commit:
            task.save()
            self.save_m2m()
            task.assignees.set(selected_assignees)
        return task
