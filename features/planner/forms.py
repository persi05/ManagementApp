from django import forms
from django.utils import timezone

from .models import LeaveRequest


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ('start_date', 'end_date', 'reason')
        labels = {
            'start_date': 'Od',
            'end_date': 'Do',
            'reason': 'Powód',
        }
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get('start_date')
        end_date = cleaned.get('end_date')
        today = timezone.localdate()
        if start_date and start_date < today:
            self.add_error('start_date', 'Nie można brać wolnego w przeszłości.')
        if end_date and end_date < today:
            self.add_error('end_date', 'Nie można brać wolnego w przeszłości.')
        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', 'Data końca nie może być wcześniejsza niż data początku.')
        return cleaned
