from django import forms

from .models import TimeEntry
from .models import employee_time_entry_edit_deadline


class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = ('project', 'start', 'end', 'comment')
        labels = {
            'project': 'Projekt',
            'start': 'Rozpoczęcie pracy',
            'end': 'Zakończenie pracy',
            'comment': 'Komentarz',
        }
        help_texts = {
            'start': 'Podaj datę i godzinę rozpoczęcia pracy.',
            'end': 'Podaj datę i godzinę zakończenia pracy. Wpis czasu pracy musi mieć konkretny koniec.',
            'comment': 'Opcjonalnie opisz korektę, np. "zapomniałem uruchomić licznik".',
        }
        widgets = {
            'start': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['start'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['end'].input_formats = ['%Y-%m-%dT%H:%M']

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
        instance.editable_until = employee_time_entry_edit_deadline(instance.start)
        if commit:
            instance.save()
        return instance
