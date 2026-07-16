from io import BytesIO
import shutil
import tempfile
import zipfile

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from features.accounts.models import UserProfile

from .models import DocumentAccess, DocumentItem, DocumentPin, DocumentVisibilityBlock


class DocumentTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp()
        cls._override_media_root = override_settings(MEDIA_ROOT=cls._media_root)
        cls._override_media_root.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override_media_root.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def test_user_can_create_folder_and_document(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        folder_response = self.client.post(reverse('documents'), {
            'form': 'folder',
            'name': 'Specyfikacje',
        })
        folder = DocumentItem.objects.get(name='Specyfikacje')
        document_response = self.client.post(reverse('documents'), {
            'form': 'document',
            'parent': folder.id,
            'name': 'Opis API',
            'content': 'Treść dokumentu',
        })

        self.assertEqual(folder_response.status_code, 302)
        self.assertEqual(folder_response['Location'], reverse('documents'))
        self.assertEqual(document_response.status_code, 302)
        document = DocumentItem.objects.get(name='Opis API')
        self.assertEqual(document.parent, folder)
        self.assertEqual(document.owner, user)

    def test_role_access_makes_document_visible(self):
        owner = User.objects.create_user(username='owner', password='pass')
        client = User.objects.create_user(username='client', password='pass')
        owner.profile.role = UserProfile.Role.EMPLOYEE
        owner.profile.save()
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        document = DocumentItem.objects.create(
            owner=owner,
            name='Oferta dla klienta',
            kind=DocumentItem.Kind.DOCUMENT,
            content='Widoczne',
        )
        DocumentAccess.objects.create(item=document, role=UserProfile.Role.CLIENT)

        self.client.force_login(client)
        response = self.client.get(reverse('documents'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Oferta dla klienta')

    def test_visibility_block_overrides_role_access(self):
        owner = User.objects.create_user(username='owner', password='pass')
        client = User.objects.create_user(username='client', password='pass')
        owner.profile.role = UserProfile.Role.EMPLOYEE
        owner.profile.save()
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        document = DocumentItem.objects.create(
            owner=owner,
            name='Ukryta oferta',
            kind=DocumentItem.Kind.DOCUMENT,
            content='Niewidoczne',
        )
        DocumentAccess.objects.create(item=document, role=UserProfile.Role.CLIENT)
        DocumentVisibilityBlock.objects.create(item=document, user=client)

        self.client.force_login(client)
        response = self.client.get(reverse('documents'))
        download_response = self.client.get(reverse('download_document', args=[document.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Ukryta oferta')
        self.assertEqual(download_response.status_code, 404)

    def test_manage_access_does_not_allow_rename_without_edit_access(self):
        owner = User.objects.create_user(username='owner', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        owner.profile.role = UserProfile.Role.EMPLOYEE
        owner.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        document = DocumentItem.objects.create(owner=owner, name='Stara nazwa', kind=DocumentItem.Kind.DOCUMENT)
        DocumentAccess.objects.create(item=document, user=employee, can_manage=True, can_edit=False)

        self.client.force_login(employee)
        response = self.client.post(reverse('documents'), {
            'form': 'rename',
            'item': document.id,
            'name': 'Nowa nazwa',
        })

        document.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(document.name, 'Stara nazwa')

    def test_user_access_without_permissions_overrides_role_edit_and_manage(self):
        owner = User.objects.create_user(username='owner', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        owner.profile.role = UserProfile.Role.MANAGEMENT
        owner.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        folder = DocumentItem.objects.create(owner=owner, name='Folder', kind=DocumentItem.Kind.FOLDER)
        document = DocumentItem.objects.create(owner=owner, name='Stara nazwa', kind=DocumentItem.Kind.DOCUMENT)
        DocumentAccess.objects.create(item=document, role=UserProfile.Role.EMPLOYEE, can_edit=True, can_manage=True)
        DocumentAccess.objects.create(item=document, user=employee, can_edit=False, can_manage=False)
        DocumentAccess.objects.create(item=folder, user=employee)

        self.client.force_login(employee)
        page = self.client.get(reverse('documents'))
        rename_response = self.client.post(reverse('documents'), {
            'form': 'rename',
            'item': document.id,
            'name': 'Nowa nazwa',
        })
        move_response = self.client.post(reverse('documents'), {
            'form': 'move',
            'item': document.id,
            'target_parent': folder.id,
        })

        document.refresh_from_db()
        self.assertEqual(rename_response.status_code, 403)
        self.assertEqual(move_response.status_code, 403)
        self.assertEqual(document.name, 'Stara nazwa')
        self.assertIsNone(document.parent)
        self.assertNotContains(page, '#rename')
        self.assertNotContains(page, '#move')

    def test_project_member_can_see_task_attachment_without_edit_or_manage(self):
        owner = User.objects.create_user(username='owner', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        owner.profile.role = UserProfile.Role.EMPLOYEE
        owner.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        from features.projects.models import Project, ProjectAssignment
        from features.tasks.models import Attachment, BoardColumn, Task

        project = Project.objects.create(name='Projekt')
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Start', position=0)
        task = Task.objects.create(project=project, column=column, title='Zadanie')
        document = DocumentItem.objects.create(owner=owner, name='Brief', kind=DocumentItem.Kind.DOCUMENT, content='Opis')
        Attachment.objects.create(task=task, document=document, name='Brief')

        self.client.force_login(employee)
        response = self.client.get(reverse('documents'))

        self.assertContains(response, 'Brief')
        self.assertFalse(document.can_edit(employee))
        self.assertFalse(document.can_manage(employee))

    def test_edit_access_allows_text_document_content_change(self):
        owner = User.objects.create_user(username='owner', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        owner.profile.role = UserProfile.Role.EMPLOYEE
        owner.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        document = DocumentItem.objects.create(owner=owner, name='Dokument', kind=DocumentItem.Kind.DOCUMENT, content='Stara treść')
        DocumentAccess.objects.create(item=document, user=employee, can_edit=True, can_manage=False)

        self.client.force_login(employee)
        response = self.client.post(reverse('documents'), {
            'form': 'edit_document',
            'item': document.id,
            'name': 'Nowy dokument',
            'content': 'Nowa treść',
        })

        document.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(document.name, 'Nowy dokument')
        self.assertEqual(document.content, 'Nowa treść')

    def test_copy_action_is_disabled(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        document = DocumentItem.objects.create(owner=user, name='Dokument', kind=DocumentItem.Kind.DOCUMENT, content='Treść')

        self.client.force_login(user)
        response = self.client.post(reverse('documents'), {
            'form': 'action',
            'item': document.id,
            'action': 'copy',
        })

        self.assertEqual(response.status_code, 403)
        self.assertEqual(DocumentItem.objects.filter(name__startswith='Kopia').count(), 0)

    def test_access_list_shows_manage_and_edit_when_both_are_enabled(self):
        manager = User.objects.create_user(username='manager', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        document = DocumentItem.objects.create(owner=manager, name='Procedura', kind=DocumentItem.Kind.DOCUMENT)
        DocumentAccess.objects.create(item=document, user=employee, can_manage=True, can_edit=True)

        self.client.force_login(manager)
        response = self.client.get(reverse('documents'), {'selected': document.id})

        self.assertContains(response, 'employee / zarządzanie + edycja')

    def test_access_post_merges_existing_user_permissions(self):
        manager = User.objects.create_user(username='manager', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        document = DocumentItem.objects.create(owner=manager, name='Procedura', kind=DocumentItem.Kind.DOCUMENT)
        DocumentAccess.objects.create(item=document, user=employee, can_edit=True, can_manage=False)

        self.client.force_login(manager)
        response = self.client.post(reverse('documents'), {
            'form': 'access',
            'item': document.id,
            'user': employee.id,
            'role': '',
            'can_manage': 'on',
        })

        access = DocumentAccess.objects.get(item=document, user=employee)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(access.can_edit)
        self.assertTrue(access.can_manage)
        self.assertEqual(DocumentAccess.objects.filter(item=document, user=employee).count(), 1)

    def test_uploaded_file_can_be_downloaded(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        response = self.client.post(reverse('documents'), {
            'form': 'upload',
            'name': 'plik.txt',
            'file': SimpleUploadedFile('plik.txt', b'abc', content_type='text/plain'),
        })
        item = DocumentItem.objects.get(name='plik.txt')
        download = self.client.get(reverse('download_document', args=[item.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b''.join(download.streaming_content), b'abc')

    def test_uploaded_file_can_be_opened_through_protected_view(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        item = DocumentItem.objects.create(
            owner=user,
            name='umowa.pdf',
            kind=DocumentItem.Kind.FILE,
            file=SimpleUploadedFile('umowa.pdf', b'%PDF-1.4', content_type='application/pdf'),
        )

        self.client.force_login(user)
        response = self.client.get(reverse('document_file', args=[item.id]))
        open_response = self.client.get(reverse('open_document', args=[item.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-1.4')
        self.assertEqual(open_response.status_code, 302)
        self.assertEqual(open_response['Location'], reverse('document_file', args=[item.id]))

    def test_folder_download_is_zip_with_nested_structure(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        folder = DocumentItem.objects.create(owner=user, name='Projekt', kind=DocumentItem.Kind.FOLDER)
        nested = DocumentItem.objects.create(owner=user, name='Etap 1', kind=DocumentItem.Kind.FOLDER, parent=folder)
        DocumentItem.objects.create(
            owner=user,
            name='notatki',
            kind=DocumentItem.Kind.DOCUMENT,
            parent=folder,
            content='Treść dokumentu',
        )
        DocumentItem.objects.create(
            owner=user,
            name='plik',
            kind=DocumentItem.Kind.FILE,
            parent=nested,
            file=SimpleUploadedFile('plik.txt', b'abc', content_type='text/plain'),
        )

        self.client.force_login(user)
        response = self.client.get(reverse('download_document', args=[folder.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn('Projekt.zip', response['Content-Disposition'])
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            names = set(archive.namelist())
            self.assertIn('Projekt/', names)
            self.assertIn('Projekt/Etap_1/', names)
            self.assertIn('Projekt/notatki.txt', names)
            self.assertIn('Projekt/Etap_1/plik.txt', names)
            self.assertEqual(archive.read('Projekt/notatki.txt').decode('utf-8'), 'Treść dokumentu')
            self.assertEqual(archive.read('Projekt/Etap_1/plik.txt'), b'abc')

    def test_upload_uses_filename_when_name_is_blank(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        response = self.client.post(reverse('documents'), {
            'form': 'upload',
            'name': '',
            'file': SimpleUploadedFile('oryginal.pdf', b'abc', content_type='application/pdf'),
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(DocumentItem.objects.filter(name='oryginal.pdf').exists())

    def test_upload_rejects_disallowed_extension(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        response = self.client.post(reverse('documents'), {
            'form': 'upload',
            'name': 'setup.exe',
            'file': SimpleUploadedFile('setup.exe', b'abc', content_type='application/octet-stream'),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nie mozna dodac pliku z rozszerzeniem .exe')
        self.assertFalse(DocumentItem.objects.filter(name='setup.exe').exists())

    @override_settings(DOCUMENTS_MAX_UPLOAD_SIZE_BYTES=2)
    def test_upload_rejects_file_over_size_limit(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        response = self.client.post(reverse('documents'), {
            'form': 'upload',
            'name': 'duzy.pdf',
            'file': SimpleUploadedFile('duzy.pdf', b'abc', content_type='application/pdf'),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Plik jest za duzy')
        self.assertFalse(DocumentItem.objects.filter(name='duzy.pdf').exists())

    @override_settings(DOCUMENTS_MAX_FILES_PER_USER=1)
    def test_upload_rejects_when_user_file_limit_is_reached(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        DocumentItem.objects.create(
            owner=user,
            name='istniejacy.pdf',
            kind=DocumentItem.Kind.FILE,
            file=SimpleUploadedFile('istniejacy.pdf', b'abc', content_type='application/pdf'),
        )

        self.client.force_login(user)
        response = self.client.post(reverse('documents'), {
            'form': 'upload',
            'name': 'kolejny.pdf',
            'file': SimpleUploadedFile('kolejny.pdf', b'abc', content_type='application/pdf'),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Osiagnieto limit 1 plikow')
        self.assertFalse(DocumentItem.objects.filter(name='kolejny.pdf').exists())

    def test_client_cannot_manage_access_even_for_owned_document(self):
        client = User.objects.create_user(username='client', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        document = DocumentItem.objects.create(owner=client, name='Klient doc', kind=DocumentItem.Kind.DOCUMENT)

        self.client.force_login(client)
        response = self.client.post(reverse('documents'), {
            'form': 'access',
            'item': document.id,
            'user': employee.id,
        })

        self.assertEqual(response.status_code, 403)
        self.assertFalse(DocumentAccess.objects.filter(item=document, user=employee).exists())

    def test_archive_tab_shows_archived_items(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        DocumentItem.objects.create(owner=user, name='Aktywny', kind=DocumentItem.Kind.DOCUMENT)
        DocumentItem.objects.create(owner=user, name='Archiwalny', kind=DocumentItem.Kind.DOCUMENT, is_archived=True)

        self.client.force_login(user)
        active_response = self.client.get(reverse('documents'))
        archived_response = self.client.get(reverse('documents'), {'archived': '1'})

        self.assertContains(active_response, 'Aktywny')
        self.assertNotContains(active_response, 'Archiwalny')
        self.assertContains(archived_response, 'Archiwalny')
        self.assertNotContains(archived_response, 'Aktywny')

    def test_archived_uploaded_text_file_has_preview(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        item = DocumentItem.objects.create(
            owner=user,
            name='aktualne_zadania',
            kind=DocumentItem.Kind.FILE,
            file=SimpleUploadedFile('aktualne_zadania.txt', b'Zawartosc pliku z pulpitu', content_type='text/plain'),
            is_archived=True,
        )

        self.client.force_login(user)
        response = self.client.get(reverse('documents'), {'archived': '1', 'selected': item.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'documents-preview-shell')
        self.assertContains(response, 'Zawartosc pliku z pulpitu')

    def test_archive_tab_is_global_not_current_folder(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        folder = DocumentItem.objects.create(owner=user, name='Folder 4', kind=DocumentItem.Kind.FOLDER)
        DocumentItem.objects.create(owner=user, name='Archiwum globalne', kind=DocumentItem.Kind.DOCUMENT, is_archived=True)

        self.client.force_login(user)
        response = self.client.get(reverse('documents'), {'folder': folder.id, 'archived': '1'})

        self.assertContains(response, 'Archiwum globalne')
        self.assertContains(response, 'Dokumenty i pliki')
        self.assertNotContains(response, '/ Folder 4')

    def test_folder_selection_does_not_open_preview(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        folder = DocumentItem.objects.create(owner=user, name='Folder', kind=DocumentItem.Kind.FOLDER)

        self.client.force_login(user)
        response = self.client.get(reverse('documents'), {'selected': folder.id})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'documents-preview-shell')

    def test_nested_folder_has_back_button(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        parent = DocumentItem.objects.create(owner=user, name='Nadrzędny', kind=DocumentItem.Kind.FOLDER)
        child = DocumentItem.objects.create(owner=user, name='Folder 4', kind=DocumentItem.Kind.FOLDER, parent=parent)

        self.client.force_login(user)
        response = self.client.get(reverse('documents'), {'folder': child.id})

        self.assertContains(response, 'aria-label="Wróć do poprzedniego folderu"')
        self.assertContains(response, f'?folder={parent.id}')

    def test_delete_inside_folder_returns_to_same_folder(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        folder = DocumentItem.objects.create(owner=user, name='Folder', kind=DocumentItem.Kind.FOLDER)
        document = DocumentItem.objects.create(owner=user, name='Do usunięcia', kind=DocumentItem.Kind.DOCUMENT, parent=folder)

        self.client.force_login(user)
        response = self.client.post(reverse('documents'), {
            'form': 'action',
            'item': document.id,
            'action': 'delete',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], f'{reverse("documents")}?folder={folder.id}')

    def test_delete_uploaded_document_removes_file_from_storage(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        item = DocumentItem.objects.create(
            owner=user,
            name='do_usuniecia.pdf',
            kind=DocumentItem.Kind.FILE,
            file=SimpleUploadedFile('do_usuniecia.pdf', b'abc', content_type='application/pdf'),
        )
        file_name = item.file.name

        self.client.force_login(user)
        response = self.client.post(reverse('documents'), {
            'form': 'action',
            'item': item.id,
            'action': 'delete',
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(default_storage.exists(file_name))

    def test_delete_uploaded_document_keeps_file_when_copy_still_uses_it(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        item = DocumentItem.objects.create(
            owner=user,
            name='wspoldzielony.pdf',
            kind=DocumentItem.Kind.FILE,
            file=SimpleUploadedFile('wspoldzielony.pdf', b'abc', content_type='application/pdf'),
        )
        copy = DocumentItem.objects.create(
            owner=user,
            name='kopia.pdf',
            kind=DocumentItem.Kind.FILE,
            file=item.file,
        )
        file_name = item.file.name

        item.delete()

        self.assertTrue(default_storage.exists(file_name))
        copy.delete()
        self.assertFalse(default_storage.exists(file_name))

    def test_rename_inside_folder_returns_to_same_folder(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        folder = DocumentItem.objects.create(owner=user, name='Folder', kind=DocumentItem.Kind.FOLDER)
        document = DocumentItem.objects.create(owner=user, name='Stara nazwa', kind=DocumentItem.Kind.DOCUMENT, parent=folder)

        self.client.force_login(user)
        response = self.client.post(reverse('documents'), {
            'form': 'rename',
            'item': document.id,
            'name': 'Nowa nazwa',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], f'{reverse("documents")}?folder={folder.id}&selected={document.id}')

    def test_pin_document_does_not_open_preview(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        folder = DocumentItem.objects.create(owner=user, name='Folder', kind=DocumentItem.Kind.FOLDER)
        document = DocumentItem.objects.create(owner=user, name='Oferta', kind=DocumentItem.Kind.DOCUMENT, parent=folder)

        self.client.force_login(user)
        response = self.client.post(reverse('documents'), {
            'form': 'action',
            'item': document.id,
            'action': 'pin',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], f'{reverse("documents")}?folder={folder.id}')

    def test_client_can_pin_visible_document_without_affecting_other_users(self):
        owner = User.objects.create_user(username='pin-owner', password='pass')
        client = User.objects.create_user(username='pin-client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        document = DocumentItem.objects.create(owner=owner, name='Shared file', kind=DocumentItem.Kind.DOCUMENT)
        DocumentAccess.objects.create(item=document, user=client)
        self.client.force_login(client)

        response = self.client.post(reverse('documents'), {
            'form': 'action',
            'item': document.id,
            'action': 'pin',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(DocumentPin.objects.filter(item=document, user=client).exists())
        self.assertFalse(DocumentPin.objects.filter(item=document, user=owner).exists())

    def test_folder_can_open_management_panel_without_preview(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        folder = DocumentItem.objects.create(owner=user, name='Folder do przeniesienia', kind=DocumentItem.Kind.FOLDER)

        self.client.force_login(user)
        response = self.client.get(reverse('documents'), {'manage': folder.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'documents-preview-shell')
        self.assertContains(response, f'<input type="hidden" name="item" value="{folder.id}">')
        self.assertContains(response, 'id="move"')
        self.assertNotContains(response, 'preview-frame')

    def test_management_access_change_on_folder_keeps_management_panel_open(self):
        manager = User.objects.create_user(username='manager', password='pass')
        client = User.objects.create_user(username='client', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        folder = DocumentItem.objects.create(owner=manager, name='Folder klienta', kind=DocumentItem.Kind.FOLDER)

        self.client.force_login(manager)
        response = self.client.post(reverse('documents'), {
            'form': 'access',
            'item': folder.id,
            'user': client.id,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], f'{reverse("documents")}?manage={folder.id}')
        self.assertTrue(DocumentAccess.objects.filter(item=folder, user=client).exists())

    def test_items_render_with_folders_before_files(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        DocumentItem.objects.create(owner=user, name='sort-plik', kind=DocumentItem.Kind.FILE, file=SimpleUploadedFile('sort-plik.txt', b'abc', content_type='text/plain'))
        DocumentItem.objects.create(owner=user, name='sort-folder', kind=DocumentItem.Kind.FOLDER)
        DocumentItem.objects.create(owner=user, name='sort-dokument', kind=DocumentItem.Kind.DOCUMENT, content='x')

        self.client.force_login(user)
        response = self.client.get(reverse('documents'))
        body = response.content.decode('utf-8')

        self.assertLess(body.index('<strong>sort-folder</strong>'), body.index('<strong>sort-dokument</strong>'))
        self.assertLess(body.index('<strong>sort-dokument</strong>'), body.index('<strong>sort-plik</strong>'))

    def test_search_result_shows_nested_folder_path(self):
        user = User.objects.create_user(username='owner', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        parent = DocumentItem.objects.create(owner=user, name='Projekt', kind=DocumentItem.Kind.FOLDER)
        child = DocumentItem.objects.create(owner=user, name='Umowy', kind=DocumentItem.Kind.FOLDER, parent=parent)
        item = DocumentItem.objects.create(owner=user, name='faktura-lipiec.pdf', kind=DocumentItem.Kind.FILE, parent=child, file=SimpleUploadedFile('faktura-lipiec.pdf', b'abc', content_type='application/pdf'))

        self.client.force_login(user)
        response = self.client.get(reverse('documents'), {'q': 'faktura'})

        self.assertContains(response, 'faktura-lipiec.pdf')
        self.assertContains(response, 'Lokalizacja: Projekt / Umowy')
        self.assertContains(response, f'?q=faktura&selected=')
        self.assertContains(response, f'?folder={child.id}')

        preview_response = self.client.get(reverse('documents'), {'q': 'faktura', 'selected': item.id})

        self.assertContains(preview_response, 'documents-preview-shell')
        self.assertContains(preview_response, f'href="{reverse("documents")}?q=faktura"')
