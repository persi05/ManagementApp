from datetime import timedelta

from django import forms
from django.utils import timezone

from features.accounts.models import UserProfile

from .models import EmployeeCharge, HourlyRate


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

    def clean(self):
        cleaned = super().clean()
        valid_from = cleaned.get('valid_from')
        valid_to = cleaned.get('valid_to')

        if valid_from and timezone.localdate() > retroactive_rate_change_cutoff(valid_from):
            self.add_error(
                'valid_from',
                'Stawkę za ten miesiąc można zmienić najpóźniej do 10. dnia następnego miesiąca.',
            )

        if valid_from and valid_to and valid_to < valid_from:
            self.add_error('valid_to', 'Data końca nie może być wcześniejsza niż data początku.')

        return cleaned


class EmployeeChargeForm(forms.ModelForm):
    starts_at = forms.DateTimeField(
        required=False,
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}),
    )

    class Meta:
        model = EmployeeCharge
        fields = ('name', 'amount', 'starts_at')
        labels = {
            'name': 'Rodzaj obciążenia',
            'amount': 'Kwota',
            'starts_at': 'Data i godzina',
        }
        help_texts = {
            'amount': 'Kwota dodatnia pomniejsza wypłatę, a ujemna ją zwiększa.',
            'starts_at': 'Opcjonalnie. Jeśli pozostawisz puste, zostanie użyta aktualna data i godzina.',
        }
        widgets = {
            'amount': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get('amount')
        starts_at = cleaned.get('starts_at')

        if amount == 0:
            self.add_error('amount', 'Kwota obciążenia nie może wynosić 0,00 zł.')

        if not starts_at:
            starts_at = timezone.now()
            cleaned['starts_at'] = starts_at

        return cleaned


def retroactive_rate_change_cutoff(valid_from):
    first_next_month = (valid_from.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first_next_month + timedelta(days=9)
