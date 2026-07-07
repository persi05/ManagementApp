from django import forms
from django.utils import timezone

from .models import TimeEntry


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
            'comment': 'Opcjonalnie opisz korektę, np. "zapomniałem uruchomić licznik".',
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
