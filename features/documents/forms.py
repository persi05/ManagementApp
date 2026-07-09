from django import forms
from django.contrib.auth.models import User

from features.accounts.models import UserProfile

from .models import DocumentAccess, DocumentItem


class FolderForm(forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ('name',)
        labels = {'name': 'Nazwa folderu'}


class TextDocumentForm(forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ('name', 'content')
        labels = {'name': 'Nazwa dokumentu', 'content': 'Treść'}
        widgets = {'content': forms.Textarea(attrs={'rows': 5})}


class UploadDocumentForm(forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ('name', 'file')
        labels = {'name': 'Nazwa', 'file': 'Plik lub zdjęcie'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = False


class RenameDocumentForm(forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ('name',)
        labels = {'name': 'Nowa nazwa'}


class DocumentAccessForm(forms.ModelForm):
    class Meta:
        model = DocumentAccess
        fields = ('user', 'role', 'can_edit', 'can_manage')
        labels = {
            'user': 'Użytkownik',
            'role': 'Rola',
            'can_edit': 'Może edytować (zmiana nazwy i treści dokumentu)',
            'can_manage': 'Może zarządzać (przenoszenie, archiwizacja, usuwanie i kopiowanie)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.filter(is_active=True).order_by('username')
        self.fields['user'].required = False
        self.fields['role'].required = False
        self.fields['role'].choices = [('', 'Wybierz rolę')] + list(UserProfile.Role.choices)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('user') and not cleaned.get('role'):
            raise forms.ValidationError('Wybierz rolę albo konkretnego użytkownika.')
        return cleaned
