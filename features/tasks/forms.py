from django import forms

from .models import Task, TaskWorklog


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
