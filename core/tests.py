from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import EmployeeProfileForm, ProjectAssignmentForm
from .models import BoardColumn, Project, ProjectAssignment, Task, TaskWorklog, TimeEntry, UserProfile, WorkSession
from .selectors import visible_projects


class RoutingTests(TestCase):
    def test_account_routes_are_namespaced(self):
        self.assertEqual(reverse('accounts:login'), '/accounts/login/')
        self.assertEqual(reverse('accounts:register'), '/accounts/register/')
        self.assertEqual(reverse('accounts:settings'), '/accounts/settings/')

    def test_workspace_routes_live_under_app_prefix(self):
        self.assertEqual(reverse('projects'), '/app/projects/')
        self.assertEqual(reverse('employees'), '/app/employees/')
        self.assertEqual(reverse('time_entries'), '/app/time-entries/')


class RegistrationTests(TestCase):
    def test_registered_user_gets_client_role(self):
        response = self.client.post(reverse('accounts:register'), {
            'username': 'newclient',
            'email': 'client@example.com',
            'first_name': 'Jan',
            'last_name': 'Klient',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='newclient')
        self.assertEqual(user.profile.role, UserProfile.Role.CLIENT)


class AdminAccessTests(TestCase):
    def test_admin_is_forbidden_for_non_management_user(self):
        user = User.objects.create_user(username='employee', password='pass', is_staff=True)
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        response = self.client.get('/admin/')

        self.assertEqual(response.status_code, 403)


class ProjectVisibilityTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(username='client', password='pass')
        self.employee = User.objects.create_user(username='employee', password='pass')
        self.manager = User.objects.create_user(username='manager', password='pass')

        self.client_user.profile.role = UserProfile.Role.CLIENT
        self.client_user.profile.save()
        self.employee.profile.role = UserProfile.Role.EMPLOYEE
        self.employee.profile.save()
        self.manager.profile.role = UserProfile.Role.MANAGEMENT
        self.manager.profile.save()

        self.client_project = Project.objects.create(name='Client project', client=self.client_user)
        self.employee_project = Project.objects.create(name='Employee project')
        self.hidden_project = Project.objects.create(name='Hidden project')
        ProjectAssignment.objects.create(project=self.employee_project, user=self.employee)

    def test_client_sees_own_projects(self):
        self.assertEqual(list(visible_projects(self.client_user).order_by('name')), [self.client_project])

    def test_employee_sees_assigned_projects(self):
        self.assertEqual(list(visible_projects(self.employee).order_by('name')), [self.employee_project])

    def test_management_sees_all_projects(self):
        self.assertEqual(
            list(visible_projects(self.manager).order_by('name')),
            [self.client_project, self.employee_project, self.hidden_project],
        )


class TimerTests(TestCase):
    def test_timer_accepts_blank_project_and_task(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        response = self.client.post(reverse('start_timer'), {'project': '', 'task': '', 'next': '/'})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(WorkSession.objects.filter(user=user, project__isnull=True, task__isnull=True).exists())

    def test_client_cannot_start_timer(self):
        user = User.objects.create_user(username='client', password='pass')
        user.profile.role = UserProfile.Role.CLIENT
        user.profile.save()

        self.client.force_login(user)
        response = self.client.post(reverse('start_timer'), {'project': '', 'task': '', 'next': '/'})

        self.assertEqual(response.status_code, 403)


class ExportPdfTests(TestCase):
    def test_management_export_without_user_is_team_report(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee = User.objects.create_user(username='employee', first_name='Jan', last_name='Kowalski', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.bank_account = '12 1020 1026 0000 0422 7020 1111'
        employee.profile.save()
        start = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
        TimeEntry.objects.create(
            user=employee,
            start=start,
            end=start + timedelta(hours=8),
            editable_until=start.replace(hour=23, minute=59),
        )

        self.client.force_login(manager)
        response = self.client.get(reverse('export_pdf'), {'month': start.strftime('%Y-%m')})

        self.assertContains(response, 'Zbiorczy raport czasu pracy')
        self.assertContains(response, 'Jan Kowalski')
        self.assertContains(response, '8,00h')

    def test_client_report_uses_visible_project_worklogs(self):
        client = User.objects.create_user(username='client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        employee = User.objects.create_user(username='employee')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        ProjectAssignment.objects.create(project=project, user=employee, project_role=ProjectAssignment.ProjectRole.EMPLOYEE)
        column = BoardColumn.objects.create(project=project, name='Done')
        task = Task.objects.create(project=project, column=column, title='Visible task')
        TaskWorklog.objects.create(task=task, user=employee, hours='3.50', visible_to_client=True)

        self.client.force_login(client)
        response = self.client.get(reverse('reports'))

        self.assertContains(response, 'Client project')
        self.assertContains(response, '3,50h')


class EmployeeProfileFormTests(TestCase):
    def test_polish_bank_account_requires_26_digits(self):
        form = EmployeeProfileForm(data={'bank_account': '12345678901234567890123456', 'is_blocked': ''})

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['bank_account'], '1234 5678 9012 3456 7890 1234 56')

    def test_international_bank_account_uses_iban_format(self):
        form = EmployeeProfileForm(data={
            'bank_account': 'PL12345678901234567890123456',
            'international_account': 'on',
            'is_blocked': '',
        })

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['bank_account'], 'PL 12345678901234567890123456')

    def test_invalid_bank_account_length_is_rejected(self):
        form = EmployeeProfileForm(data={'bank_account': '1234', 'is_blocked': ''})

        self.assertFalse(form.is_valid())
        self.assertIn('bank_account', form.errors)


class ProjectAssignmentFormTests(TestCase):
    def test_client_cannot_be_assigned_as_employee(self):
        client = User.objects.create_user(username='client')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Project', client=client)

        form = ProjectAssignmentForm(data={
            'user': client.id,
            'project_role': ProjectAssignment.ProjectRole.EMPLOYEE,
        }, project=project)

        self.assertFalse(form.is_valid())
        self.assertIn('user', form.errors)


class KanbanRenderingTests(TestCase):
    def test_task_without_assignee_renders_as_unassigned(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Do zrobienia')
        Task.objects.create(project=project, column=column, title='Task without assignee')

        self.client.force_login(manager)
        response = self.client.get(reverse('kanban_project', args=[project.id]))

        self.assertContains(response, 'Nieprzypisane')

    def test_client_cannot_move_task_between_columns(self):
        client = User.objects.create_user(username='client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia')
        done = BoardColumn.objects.create(project=project, name='Zakończone')
        task = Task.objects.create(project=project, column=todo, title='Client visible task')

        self.client.force_login(client)
        response = self.client.post(reverse('move_task', args=[task.id]), {'column': done.id})

        self.assertEqual(response.status_code, 403)
        task.refresh_from_db()
        self.assertEqual(task.column, todo)
