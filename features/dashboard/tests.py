from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from features.accounts.models import UserProfile
from features.employees.forms import EmployeeProfileForm, HourlyRateForm
from features.employees.models import HourlyRate
from features.employees.services import save_hourly_rate
from features.projects.forms import ProjectAssignmentForm
from features.projects.models import Project, ProjectAssignment
from features.projects.selectors import visible_projects
from features.planner.models import LeaveRequest
from features.tasks.models import BoardColumn, Task, TaskWorklog
from features.time_tracking.models import TimeEntry, WorkSession


class RoutingTests(TestCase):
    def test_account_routes_are_namespaced(self):
        self.assertEqual(reverse('accounts:login'), '/accounts/login/')
        self.assertEqual(reverse('accounts:register'), '/accounts/register/')
        self.assertEqual(reverse('accounts:settings'), '/accounts/settings/')

    def test_workspace_routes_live_under_app_prefix(self):
        self.assertEqual(reverse('projects'), '/app/projects/')
        self.assertEqual(reverse('employees'), '/app/employees/')
        self.assertEqual(reverse('time_entries'), '/app/time-entries/')
        self.assertEqual(reverse('calendar'), '/app/calendar/')


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
    def test_admin_is_forbidden_for_non_superuser(self):
        user = User.objects.create_user(username='employee', password='pass', is_staff=True)
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        response = self.client.get('/admin/')

        self.assertEqual(response.status_code, 403)

    def test_admin_is_forbidden_for_management_without_superuser(self):
        user = User.objects.create_user(username='manager', password='pass', is_staff=True)
        user.profile.role = UserProfile.Role.MANAGEMENT
        user.profile.save()

        self.client.force_login(user)
        response = self.client.get('/admin/')

        self.assertEqual(response.status_code, 403)

    def test_admin_allows_superuser(self):
        user = User.objects.create_superuser(username='admin', password='pass')

        self.client.force_login(user)
        response = self.client.get('/admin/')

        self.assertEqual(response.status_code, 200)


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

    def test_paused_timer_renders_resume_action(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        WorkSession.objects.create(user=user, state=WorkSession.State.PAUSED, paused_at=timezone.now())

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'Wznów')
        self.assertContains(response, reverse('resume_timer'))

    def test_resume_timer_excludes_pause_from_work_time(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        session = WorkSession.objects.create(
            user=user,
            state=WorkSession.State.PAUSED,
            started_at=timezone.now() - timedelta(minutes=30),
            paused_at=timezone.now() - timedelta(minutes=10),
        )

        self.client.force_login(user)
        response = self.client.post(reverse('resume_timer'), {'next': '/'})

        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.state, WorkSession.State.RUNNING)
        self.assertIsNone(session.paused_at)
        self.assertGreaterEqual(session.inactive_minutes, 9)

    def test_stop_paused_timer_excludes_pause_duration(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        WorkSession.objects.create(
            user=user,
            state=WorkSession.State.PAUSED,
            started_at=timezone.now() - timedelta(minutes=60),
            paused_at=timezone.now() - timedelta(minutes=30),
        )

        self.client.force_login(user)
        response = self.client.post(reverse('stop_timer'), {'next': '/'})

        self.assertEqual(response.status_code, 302)
        entry = TimeEntry.objects.get(user=user)
        self.assertLessEqual(entry.duration_minutes, 31)


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


class CalendarTests(TestCase):
    def test_employee_calendar_shows_work_hours_and_task_deadline(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        project = Project.objects.create(name='Calendar project')
        ProjectAssignment.objects.create(project=project, user=user)
        column = BoardColumn.objects.create(project=project, name='Todo')
        day = timezone.localdate().replace(day=5)
        Task.objects.create(project=project, column=column, title='Deadline task', assignee=user, due_date=day)
        start = timezone.make_aware(datetime.combine(day, time(hour=9)))
        TimeEntry.objects.create(
            user=user,
            project=project,
            start=start,
            end=start + timedelta(hours=8),
            editable_until=start.replace(hour=23, minute=59),
        )

        self.client.force_login(user)
        response = self.client.get(reverse('calendar'), {'month': day.strftime('%Y-%m')})

        self.assertContains(response, '8,00h')
        self.assertContains(response, 'Deadline task')

    def test_employee_can_request_leave(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        response = self.client.post(reverse('calendar'), {
            'form': 'leave_request',
            'start_date': '2026-07-20',
            'end_date': '2026-07-22',
            'reason': 'Urlop',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(LeaveRequest.objects.filter(user=user, status=LeaveRequest.Status.PENDING).exists())

    def test_management_calendar_shows_employee_presence(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee = User.objects.create_user(username='employee', first_name='Jan', last_name='Nowak', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        day = timezone.localdate().replace(day=6)
        start = timezone.make_aware(datetime.combine(day, time(hour=8)))
        TimeEntry.objects.create(
            user=employee,
            start=start,
            end=start + timedelta(hours=6),
            editable_until=start.replace(hour=23, minute=59),
        )

        self.client.force_login(manager)
        response = self.client.get(reverse('calendar'), {'month': day.strftime('%Y-%m')})

        self.assertContains(response, 'Jan Nowak')
        self.assertContains(response, '6,00h')

    def test_client_calendar_does_not_show_leave_request_form(self):
        client = User.objects.create_user(username='client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()

        self.client.force_login(client)
        response = self.client.get(reverse('calendar'))

        self.assertNotContains(response, 'Wyślij wniosek')
        self.assertNotContains(response, 'Moje wnioski')


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


class HourlyRateFormTests(TestCase):
    def test_rate_for_previous_month_can_be_changed_until_tenth_day(self):
        with patch('features.employees.forms.timezone.localdate', return_value=date(2026, 6, 10)):
            form = HourlyRateForm(data={
                'amount': '30.00',
                'currency': 'PLN',
                'valid_from': '2026-05-01',
                'valid_to': '',
            })
            self.assertTrue(form.is_valid())

    def test_rate_for_previous_month_is_blocked_after_tenth_day(self):
        with patch('features.employees.forms.timezone.localdate', return_value=date(2026, 6, 11)):
            form = HourlyRateForm(data={
                'amount': '30.00',
                'currency': 'PLN',
                'valid_from': '2026-05-01',
                'valid_to': '',
            })
            self.assertFalse(form.is_valid())
            self.assertIn('valid_from', form.errors)

    def test_saving_same_effective_date_updates_existing_rate(self):
        user = User.objects.create_user(username='employee')
        manager = User.objects.create_user(username='manager')
        HourlyRate.objects.create(user=user, amount=Decimal('30.50'), currency='PLN', valid_from=date(2026, 5, 1), created_by=manager)

        save_hourly_rate(user, {
            'amount': Decimal('30.00'),
            'currency': 'PLN',
            'valid_from': date(2026, 5, 1),
            'valid_to': None,
        }, manager)

        self.assertEqual(HourlyRate.objects.filter(user=user).count(), 1)
        self.assertEqual(HourlyRate.objects.get(user=user).amount, Decimal('30.00'))

    def test_new_rate_closes_previous_open_ended_rate(self):
        user = User.objects.create_user(username='employee')
        manager = User.objects.create_user(username='manager')
        previous = HourlyRate.objects.create(user=user, amount=Decimal('30.00'), currency='PLN', valid_from=date(2026, 5, 1), created_by=manager)

        save_hourly_rate(user, {
            'amount': Decimal('30.50'),
            'currency': 'PLN',
            'valid_from': date(2026, 6, 1),
            'valid_to': None,
        }, manager)

        previous.refresh_from_db()
        self.assertEqual(previous.valid_to, date(2026, 5, 31))


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

    def test_client_task_creation_defaults_to_todo_without_assignee(self):
        client = User.objects.create_user(username='client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)

        self.client.force_login(client)
        response = self.client.post(reverse('kanban_project', args=[project.id]), {
            'project': project.id,
            'title': 'Nowe zadanie klienta',
            'description': 'Opis',
            'due_date': '',
            'priority': 'medium',
        })

        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title='Nowe zadanie klienta')
        self.assertEqual(task.column, todo)
        self.assertIsNone(task.assignee)

    def test_employee_cannot_move_task_to_done(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Employee project')
        ProjectAssignment.objects.create(project=project, user=employee)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        done = BoardColumn.objects.create(project=project, name='Zakończone', position=3)
        task = Task.objects.create(project=project, column=todo, title='Task for employee')

        self.client.force_login(employee)
        response = self.client.post(reverse('move_task', args=[task.id]), {'column': done.id})

        self.assertEqual(response.status_code, 403)
        task.refresh_from_db()
        self.assertEqual(task.column, todo)

    def test_employee_cannot_choose_done_column_in_task_form(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Employee project')
        ProjectAssignment.objects.create(project=project, user=employee)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        BoardColumn.objects.create(project=project, name='W trakcie', position=1)
        BoardColumn.objects.create(project=project, name='Review', position=2)
        done = BoardColumn.objects.create(project=project, name='Zakończone', position=3)

        self.client.force_login(employee)
        response = self.client.post(reverse('kanban_project', args=[project.id]), {
            'project': project.id,
            'column': done.id,
            'title': 'Task for employee',
            'description': 'Opis',
            'due_date': '',
            'priority': 'medium',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Task.objects.filter(title='Task for employee').exists())
        self.assertContains(response, 'Wybierz poprawną wartość')

    def test_employee_does_not_see_drop_hint_in_done_column(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Employee project')
        ProjectAssignment.objects.create(project=project, user=employee)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        doing = BoardColumn.objects.create(project=project, name='W trakcie', position=1)
        review = BoardColumn.objects.create(project=project, name='Review', position=2)
        done = BoardColumn.objects.create(project=project, name='Zakończone', position=3)
        Task.objects.create(project=project, column=todo, title='Task todo')
        Task.objects.create(project=project, column=doing, title='Task doing')
        Task.objects.create(project=project, column=review, title='Task review')

        self.client.force_login(employee)
        response = self.client.get(reverse('kanban_project', args=[project.id]))

        self.assertNotContains(response, 'Upuść tu zadanie.')

    def test_lead_can_move_task_to_done(self):
        lead = User.objects.create_user(username='lead', password='pass')
        lead.profile.role = UserProfile.Role.EMPLOYEE
        lead.profile.save()
        project = Project.objects.create(name='Lead project')
        ProjectAssignment.objects.create(project=project, user=lead, project_role=ProjectAssignment.ProjectRole.LEAD)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        done = BoardColumn.objects.create(project=project, name='Zakończone', position=3)
        task = Task.objects.create(project=project, column=todo, title='Task for lead')

        self.client.force_login(lead)
        response = self.client.post(reverse('move_task', args=[task.id]), {'column': done.id})

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.column, done)

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
