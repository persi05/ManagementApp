from io import BytesIO
import posixpath
import zipfile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_POST

from features.accounts.models import is_management

from .forms import DocumentAccessForm, FolderForm, RenameDocumentForm, TextDocumentForm, UploadDocumentForm
from .models import DocumentAccess, DocumentItem


TEXT_PREVIEW_EXTENSIONS = {
    'csv',
    'css',
    'html',
    'js',
    'json',
    'log',
    'md',
    'py',
    'sql',
    'txt',
    'xml',
    'yaml',
    'yml',
}
TEXT_PREVIEW_BYTES = 64 * 1024
TEXT_PREVIEW_MAX_FILE_SIZE = 256 * 1024


def visible_document(user, item_id):
    return get_object_or_404(DocumentItem.visible_to(user), pk=item_id)


def parent_from_request(request):
    parent_id = request.POST.get('parent') or request.GET.get('folder')
    if not parent_id:
        return None
    parent = visible_document(request.user, parent_id)
    if parent.kind != DocumentItem.Kind.FOLDER:
        return None
    return parent


def is_descendant_folder(candidate, folder):
    cursor = candidate
    while cursor:
        if cursor.pk == folder.pk:
            return True
        cursor = cursor.parent
    return False


def classify_upload(uploaded_file):
    content_type = getattr(uploaded_file, 'content_type', '') or ''
    if content_type.startswith('image/'):
        return DocumentItem.Kind.IMAGE
    return DocumentItem.Kind.FILE


def document_file_extension(item):
    if not item or not item.file or '.' not in item.file.name:
        return ''
    return item.file.name.rsplit('.', 1)[-1].lower()


def file_preview_text(item):
    if not item or not item.file or item.kind == DocumentItem.Kind.IMAGE:
        return ''
    extension = document_file_extension(item)
    if extension == 'pdf':
        return ''
    try:
        size = item.file.size
    except OSError:
        return ''
    if extension not in TEXT_PREVIEW_EXTENSIONS and size > TEXT_PREVIEW_MAX_FILE_SIZE:
        return ''
    try:
        with item.file.open('rb') as file_handle:
            raw = file_handle.read(TEXT_PREVIEW_BYTES)
    except OSError:
        return ''
    if not raw:
        return ''
    text = raw.decode('utf-8', errors='replace')
    if text.count('\ufffd') > max(3, len(text) // 20):
        return ''
    if size > TEXT_PREVIEW_BYTES:
        return f'{text}\n\n...'
    return text


def safe_archive_name(name, fallback):
    filename = get_valid_filename(name or fallback).strip(' ._')
    return filename or fallback


def unique_archive_path(path, used_paths):
    if path not in used_paths:
        used_paths.add(path)
        return path
    directory, filename = posixpath.split(path)
    stem, dot, extension = filename.rpartition('.')
    if not dot:
        stem = filename
        extension = ''
    for counter in range(2, 10000):
        suffix = f'{stem} ({counter})'
        candidate_name = f'{suffix}.{extension}' if extension else suffix
        candidate = posixpath.join(directory, candidate_name) if directory else candidate_name
        if candidate not in used_paths:
            used_paths.add(candidate)
            return candidate
    return path


def archive_file_name(item):
    name = safe_archive_name(item.name, 'plik')
    file_extension = document_file_extension(item)
    if file_extension and '.' not in name:
        return f'{name}.{file_extension}'
    return name


def add_item_to_archive(archive, item, base_path, used_paths):
    if item.kind == DocumentItem.Kind.FOLDER:
        folder_name = safe_archive_name(item.name, 'folder')
        folder_path = posixpath.join(base_path, folder_name) if base_path else folder_name
        directory_path = unique_archive_path(f'{folder_path}/', used_paths)
        archive.writestr(directory_path, b'')
        child_base = directory_path.rstrip('/')
        for child in item.children.select_related('owner', 'parent').order_by('kind', 'name', 'id'):
            add_item_to_archive(archive, child, child_base, used_paths)
        return

    if item.file:
        file_path = posixpath.join(base_path, archive_file_name(item))
        with item.file.open('rb') as file_handle:
            archive.writestr(unique_archive_path(file_path, used_paths), file_handle.read())
        return

    document_name = safe_archive_name(item.name, 'dokument')
    if not document_name.lower().endswith('.txt'):
        document_name = f'{document_name}.txt'
    archive.writestr(unique_archive_path(posixpath.join(base_path, document_name), used_paths), item.content or '')


def folder_archive_response(folder):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        add_item_to_archive(archive, folder, '', set())
    buffer.seek(0)
    filename = safe_archive_name(folder.name, 'folder')
    response = HttpResponse(buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}.zip"'
    return response


def documents_redirect(parent=None, selected=None, manage=None, archived=False):
    params = []
    if parent:
        params.append(f'folder={parent.id}')
    if selected:
        params.append(f'selected={selected.id}')
    if manage:
        params.append(f'manage={manage.id}')
    if archived:
        params.append('archived=1')
    suffix = f"?{'&'.join(params)}" if params else ''
    return redirect(f'{reverse("documents")}{suffix}')


@login_required
def documents(request):
    parent = parent_from_request(request)
    query = (request.GET.get('q') or '').strip()
    selected_id = request.GET.get('selected')
    manage_id = request.GET.get('manage')
    show_archived = request.GET.get('archived') == '1'
    if show_archived:
        parent = None

    if request.method == 'POST':
        parent = parent_from_request(request)
        form_name = request.POST.get('form')

        if form_name == 'folder':
            form = FolderForm(request.POST)
            if form.is_valid():
                item = form.save(commit=False)
                item.kind = DocumentItem.Kind.FOLDER
                item.parent = parent
                item.owner = request.user
                item.save()
                messages.success(request, 'Folder został utworzony.')
                return documents_redirect(parent=parent)
        elif form_name == 'document':
            form = TextDocumentForm(request.POST)
            if form.is_valid():
                item = form.save(commit=False)
                item.kind = DocumentItem.Kind.DOCUMENT
                item.parent = parent
                item.owner = request.user
                item.save()
                messages.success(request, 'Dokument został utworzony.')
                return documents_redirect(parent=parent, selected=item)
        elif form_name == 'upload':
            form = UploadDocumentForm(request.POST, request.FILES)
            if form.is_valid():
                item = form.save(commit=False)
                item.kind = classify_upload(item.file)
                item.parent = parent
                item.owner = request.user
                if not item.name:
                    item.name = item.file.name
                item.save()
                messages.success(request, 'Plik został przesłany.')
                return documents_redirect(parent=parent, selected=item)
        elif form_name == 'rename':
            item = visible_document(request.user, request.POST.get('item'))
            if not item.can_edit(request.user):
                return HttpResponseForbidden('Brak uprawnień do zmiany nazwy.')
            form = RenameDocumentForm(request.POST, instance=item)
            if form.is_valid():
                form.save()
                messages.success(request, 'Nazwa została zmieniona.')
                return documents_redirect(
                    parent=None if item.is_archived else item.parent,
                    selected=None if item.kind == DocumentItem.Kind.FOLDER else item,
                    archived=item.is_archived,
                )
        elif form_name == 'access':
            item = visible_document(request.user, request.POST.get('item'))
            if not is_management(request.user):
                return HttpResponseForbidden('Brak uprawnień do udostępniania.')
            form = DocumentAccessForm(request.POST)
            if form.is_valid():
                access = form.save(commit=False)
                access.item = item
                access.save()
                messages.success(request, 'Dostęp został dodany.')
                return documents_redirect(
                    parent=None if item.is_archived else item.parent,
                    selected=None if item.kind == DocumentItem.Kind.FOLDER else item,
                    manage=item if item.kind == DocumentItem.Kind.FOLDER else None,
                    archived=item.is_archived,
                )
        elif form_name == 'remove_access':
            if not is_management(request.user):
                return HttpResponseForbidden('Brak uprawnień do edycji dostępu.')
            access = get_object_or_404(DocumentAccess, pk=request.POST.get('access'))
            item = visible_document(request.user, access.item_id)
            access.delete()
            messages.success(request, 'Dostęp został usunięty.')
            return documents_redirect(
                parent=None if item.is_archived else item.parent,
                selected=None if item.kind == DocumentItem.Kind.FOLDER else item,
                manage=item if item.kind == DocumentItem.Kind.FOLDER else None,
                archived=item.is_archived,
            )
        elif form_name == 'move':
            item = visible_document(request.user, request.POST.get('item'))
            if not item.can_manage(request.user):
                return HttpResponseForbidden('Brak uprawnień do przenoszenia.')
            previous_parent = item.parent
            target_id = request.POST.get('target_parent')
            if target_id:
                target = visible_document(request.user, target_id)
                if target.kind != DocumentItem.Kind.FOLDER:
                    return HttpResponseForbidden('Docelowy element nie jest folderem.')
                if item.kind == DocumentItem.Kind.FOLDER and is_descendant_folder(target, item):
                    return HttpResponseForbidden('Nie można przenieść folderu do niego samego ani jego podfolderu.')
                item.parent = target
            else:
                item.parent = None
            item.save(update_fields=['parent', 'updated_at'])
            messages.success(request, 'Element został przeniesiony.')
            return documents_redirect(parent=None if item.is_archived else previous_parent, archived=item.is_archived)
        elif form_name == 'action':
            item = visible_document(request.user, request.POST.get('item'))
            action = request.POST.get('action')
            if action in {'archive', 'unarchive', 'delete', 'pin', 'copy'} and not item.can_manage(request.user):
                return HttpResponseForbidden('Brak uprawnień do tej akcji.')
            if action == 'archive':
                previous_parent = item.parent
                item.is_archived = True
                item.save(update_fields=['is_archived', 'updated_at'])
                messages.success(request, 'Element został zarchiwizowany.')
                return documents_redirect(parent=previous_parent)
            if action == 'unarchive':
                item.is_archived = False
                item.save(update_fields=['is_archived', 'updated_at'])
                messages.success(request, 'Element został przywrócony.')
                return documents_redirect(parent=item.parent, selected=item)
            if action == 'delete':
                previous_parent = item.parent
                was_archived = item.is_archived
                item.delete()
                messages.success(request, 'Element został usunięty.')
                return documents_redirect(parent=None if was_archived else previous_parent, archived=was_archived)
            if action == 'pin':
                item.is_pinned = not item.is_pinned
                item.save(update_fields=['is_pinned', 'updated_at'])
                return documents_redirect(
                    parent=None if item.is_archived else item.parent,
                    selected=None if item.kind == DocumentItem.Kind.FOLDER else item,
                    archived=item.is_archived,
                )
            if action == 'copy':
                copy = DocumentItem.objects.create(
                    name=f'Kopia {item.name}',
                    kind=item.kind,
                    parent=item.parent,
                    file=item.file,
                    content=item.content,
                    owner=request.user,
                )
                messages.success(request, 'Kopia została utworzona.')
                return documents_redirect(parent=copy.parent, selected=copy)

    items = DocumentItem.visible_to(request.user).filter(is_archived=show_archived)
    if query:
        current_items = items.filter(Q(name__icontains=query) | Q(content__icontains=query))
    else:
        current_items = items.filter(parent=parent)
    current_items = current_items.select_related('owner', 'parent').annotate(
        children_count=Count('children'),
        kind_rank=Case(
            When(kind=DocumentItem.Kind.FOLDER, then=Value(0)),
            When(kind=DocumentItem.Kind.DOCUMENT, then=Value(1)),
            When(kind=DocumentItem.Kind.IMAGE, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        ),
    )
    current_items = current_items.order_by('-is_pinned', 'kind_rank', 'name')

    selected = None
    if selected_id:
        selected = DocumentItem.visible_to(request.user).select_related('owner', 'parent').filter(pk=selected_id).first()
        if selected and selected.kind == DocumentItem.Kind.FOLDER:
            selected = None

    managed_item = None
    if manage_id:
        managed_item = DocumentItem.visible_to(request.user).select_related('owner', 'parent').filter(pk=manage_id).first()
    panel_item = selected or managed_item

    breadcrumbs = []
    cursor = parent
    while cursor:
        breadcrumbs.append(cursor)
        cursor = cursor.parent
    breadcrumbs.reverse()

    return render(request, 'features/documents.html', {
        'items': current_items,
        'parent': parent,
        'breadcrumbs': breadcrumbs,
        'query': query,
        'show_archived': show_archived,
        'selected': selected,
        'panel_item': panel_item,
        'selected_is_pdf': bool(selected and selected.file and document_file_extension(selected) == 'pdf'),
        'selected_preview_text': file_preview_text(selected),
        'folder_form': FolderForm(),
        'document_form': TextDocumentForm(),
        'upload_form': UploadDocumentForm(),
        'rename_form': RenameDocumentForm(instance=panel_item) if panel_item else RenameDocumentForm(),
        'access_form': DocumentAccessForm(),
        'accesses': panel_item.accesses.select_related('user') if panel_item else [],
        'folders': DocumentItem.visible_to(request.user).filter(kind=DocumentItem.Kind.FOLDER, is_archived=False).exclude(pk=panel_item.pk if panel_item else None),
        'can_manage_selected': panel_item.can_manage(request.user) if panel_item else False,
        'can_edit_selected': panel_item.can_edit(request.user) if panel_item else False,
        'can_manage_access': bool(panel_item and is_management(request.user)),
    })


@login_required
def download_document(request, item_id):
    item = visible_document(request.user, item_id)
    if item.kind == DocumentItem.Kind.FOLDER:
        return folder_archive_response(item)
    if item.file:
        return FileResponse(item.file.open('rb'), as_attachment=True, filename=item.name or item.file.name)
    filename = get_valid_filename(item.name or 'dokument')
    response = HttpResponse(item.content or '', content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}.txt"'
    return response


@login_required
def open_document(request, item_id):
    item = visible_document(request.user, item_id)
    if item.kind == DocumentItem.Kind.FOLDER:
        return redirect(f"{reverse('documents')}?folder={item.id}")
    if item.file:
        return HttpResponseRedirect(item.file.url)
    return redirect(f"{reverse('documents')}?selected={item.id}")
