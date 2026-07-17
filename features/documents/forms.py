from django import forms
from django.conf import settings
from django.contrib.auth.models import User

from features.accounts.models import UserProfile
from features.projects.selectors import visible_projects

from .models import DocumentAccess, DocumentItem, DocumentVisibilityBlock


def format_file_size(size):
    if size >= 1024 * 1024:
        return f'{size / (1024 * 1024):.0f} MB'
    if size >= 1024:
        return f'{size / 1024:.0f} KB'
    return f'{size} B'

def validate_document_upload(uploaded_file):
    max_size = settings.DOCUMENTS_MAX_UPLOAD_SIZE_BYTES
    if uploaded_file.size > max_size:
        raise forms.ValidationError(f'Plik jest za duzy. Maksymalny rozmiar pliku to {format_file_size(max_size)}.')

    extension = uploaded_file.name.rsplit('.', 1)[-1].lower() if '.' in uploaded_file.name else ''
    allowed_extensions = settings.DOCUMENTS_ALLOWED_UPLOAD_EXTENSIONS
    if extension not in allowed_extensions:
        allowed_label = ', '.join(sorted(allowed_extensions))
        extension_label = f'.{extension}' if extension else 'bez rozszerzenia'
        raise forms.ValidationError(f'Nie mozna dodac pliku z rozszerzeniem {extension_label}. Dozwolone rozszerzenia: {allowed_label}.')


def validate_user_file_limit(user):
    current_files_count = DocumentItem.objects.filter(owner=user).exclude(file='').count()
    if current_files_count >= settings.DOCUMENTS_MAX_FILES_PER_USER:
        raise forms.ValidationError(f'Osiagnieto limit {settings.DOCUMENTS_MAX_FILES_PER_USER} plikow dla tego uzytkownika.')


def classify_document_upload(uploaded_file):
    content_type = getattr(uploaded_file, 'content_type', '') or ''
    return DocumentItem.Kind.IMAGE if content_type.startswith('image/') else DocumentItem.Kind.FILE


class DocumentProjectFieldMixin:
    def __init__(self, *args, user=None, parent=None, **kwargs):
        super().__init__(*args, **kwargs)
        project_field = self.fields['project']
        project_field.queryset = visible_projects(user).order_by('name') if user else project_field.queryset.none()
        project_field.required = False
        project_field.empty_label = 'Prywatne'
        project_field.help_text = 'Po przypisaniu wszyscy członkowie projektu zobaczą ten element.'
        if not self.is_bound and not self.instance.pk and parent and parent.project_id:
            self.initial['project'] = parent.project_id


class FolderForm(DocumentProjectFieldMixin, forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ('name', 'project')
        labels = {'name': 'Nazwa folderu', 'project': 'Projekt'}


class TextDocumentForm(DocumentProjectFieldMixin, forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ('name', 'content', 'project')
        labels = {'name': 'Nazwa dokumentu', 'content': 'Treść', 'project': 'Projekt'}
        widgets = {'content': forms.Textarea(attrs={'rows': 5})}


class UploadDocumentForm(DocumentProjectFieldMixin, forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ('name', 'file', 'project')
        labels = {'name': 'Nazwa', 'file': 'Plik lub zdjęcie', 'project': 'Projekt'}

    def __init__(self, *args, user=None, parent=None, **kwargs):
        super().__init__(*args, user=user, parent=parent, **kwargs)
        self.user = user
        self.fields['name'].required = False

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if not uploaded_file:
            return uploaded_file

        validate_document_upload(uploaded_file)
        return uploaded_file

    def clean(self):
        cleaned = super().clean()
        if not self.user or not cleaned.get('file'):
            return cleaned

        validate_user_file_limit(self.user)
        return cleaned


class DocumentVisibilityBlockForm(forms.ModelForm):
    class Meta:
        model = DocumentVisibilityBlock
        fields = ('user',)
        labels = {'user': 'Niewidoczne dla'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.filter(is_active=True).order_by('username')


class RenameDocumentForm(forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ('name',)
        labels = {'name': 'Nowa nazwa'}


class EditTextDocumentForm(forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ('name', 'content')
        labels = {'name': 'Nazwa dokumentu', 'content': 'Treść'}
        widgets = {'content': forms.Textarea(attrs={'rows': 7})}


class DocumentProjectForm(DocumentProjectFieldMixin, forms.ModelForm):
    class Meta:
        model = DocumentItem
        fields = ('project',)
        labels = {'project': 'Projekt'}


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
