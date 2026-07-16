from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import path, reverse
from django.utils import timezone

from features.accounts.models import UserProfile
from features.documents.models import DocumentItem
from features.employees.forms import EmployeeProfileForm, HourlyRateForm
from features.employees.models import HourlyRate
from features.employees.services import save_hourly_rate
from features.projects.forms import ProjectAssignmentForm
from features.projects.models import Project, ProjectAssignment, ProjectLabelRate
from features.projects.selectors import visible_projects
from features.planner.models import LeaveRequest
from features.reports.services import payroll_amount
from features.tasks.models import Attachment, BoardColumn, Notification, Task, TaskEditNote, TaskWorklog
from features.time_tracking.models import TimeEntry, WorkSession


def raise_error(request):
    raise RuntimeError('test error')


urlpatterns = [
    path('raise-error/', raise_error),
]

handler500 = 'config.error_views.server_error'


class RoutingTests(TestCase):
    def test_account_routes_are_namespaced(self):
        self.assertEqual(reverse('accounts:login'), '/accounts/login/')
        self.assertEqual(reverse('accounts:register'), '/accounts/register/')
        self.assertEqual(reverse('accounts:settings'), '/accounts/settings/')

    def test_workspace_routes_live_under_app_prefix(self):
        self.assertEqual(reverse('dashboard'), '/app/dashboard/')
        self.assertEqual(reverse('projects'), '/app/projects/')
        self.assertEqual(reverse('employees'), '/app/employees/')
        self.assertEqual(reverse('documents'), '/app/documents/')
        self.assertEqual(reverse('time_entries'), '/app/time-entries/')
        self.assertEqual(reverse('calendar'), '/app/calendar/')

    def test_dashboard_aliases_redirect_to_current_dashboard(self):
        app_response = self.client.get('/app/')
        legacy_response = self.client.get('/dashboard/')

        self.assertEqual(app_response.status_code, 302)
        self.assertEqual(app_response['Location'], reverse('dashboard'))
        self.assertEqual(legacy_response.status_code, 302)
        self.assertEqual(legacy_response['Location'], reverse('dashboard'))

    def test_root_renders_landing_page(self):
        response = self.client.get(reverse('landing'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'landing.html')
        self.assertContains(response, 'Dcode Management')
        self.assertContains(response, reverse('accounts:login'))

    def test_login_page_hides_authenticated_header_actions(self):
        response = self.client.get(reverse('accounts:login'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Powiadomienia')
        self.assertNotContains(response, 'Moje konto')
        self.assertContains(response, 'Rejestracja')
        self.assertContains(response, f'href="{reverse("landing")}"')
        self.assertNotContains(response, 'next=/app/dashboard/')

    @override_settings(DEBUG=False)
    def test_not_found_uses_shared_error_page(self):
        response = self.client.get('/missing-page/')

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, 'error.html')
        self.assertContains(response, '404', status_code=404)
        self.assertContains(response, 'Nie znaleziono strony', status_code=404)

    def test_permission_denied_uses_shared_error_page(self):
        from config.error_views import permission_denied

        request = RequestFactory().get('/forbidden/')
        request.user = AnonymousUser()
        response = permission_denied(request, PermissionError('nope'))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, '403', status_code=403)
        self.assertContains(response, 'Brak dostępu', status_code=403)

    @override_settings(DEBUG=False, ROOT_URLCONF='features.dashboard.tests')
    def test_server_error_uses_shared_error_page(self):
        client = Client()
        client.raise_request_exception = False
        response = client.get('/raise-error/')

        self.assertEqual(response.status_code, 500)
        self.assertTemplateUsed(response, 'error.html')
        self.assertContains(response, '500', status_code=500)
        self.assertContains(response, 'Błąd aplikacji', status_code=500)


class RegistrationTests(TestCase):
    def test_registered_user_gets_client_role_and_is_logged_in(self):
        response = self.client.post(reverse('accounts:register'), {
            'username': 'newclient',
            'email': 'client@example.com',
            'first_name': 'Jan',
            'last_name': 'Klient',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))
        user = User.objects.get(username='newclient')
        self.assertEqual(user.profile.role, UserProfile.Role.CLIENT)
        self.assertTrue(user.is_active)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.id)

    def test_password_reset_route_is_removed(self):
        response = self.client.get('/accounts/password-reset/')

        self.assertEqual(response.status_code, 404)

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

    def test_projects_page_is_paginated_by_fifty(self):
        Project.objects.bulk_create([Project(name=f'Project {index:02}') for index in range(48)])
        self.client.force_login(self.manager)

        first_page = self.client.get(reverse('projects'))
        second_page = self.client.get(reverse('projects'), {'page': 2})

        self.assertEqual(len(first_page.context['projects']), 50)
        self.assertEqual(len(second_page.context['projects']), 1)

    def test_active_projects_widget_includes_project_after_a_task_is_done(self):
        done_column = BoardColumn.objects.create(project=self.hidden_project, name='Zakończone', is_done_column=True)
        Task.objects.create(project=self.hidden_project, column=done_column, title='Finished task')
        self.client.force_login(self.manager)

        response = self.client.get(reverse('dashboard'))

        projects = [row['project'] for row in response.context['project_rows']]
        self.assertEqual(projects, [self.hidden_project])

    def test_client_dashboard_hides_work_status_widget(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Postęp projektów')
        self.assertNotContains(response, 'Status pracy')


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

    def test_management_dashboard_renders_timer_panel(self):
        user = User.objects.create_user(username='manager', password='pass')
        user.profile.role = UserProfile.Role.MANAGEMENT
        user.profile.save()

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'data-timer-root')
        self.assertContains(response, reverse('timer_status'))
        self.assertContains(response, reverse('start_timer'))

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

    def test_resume_timer_excludes_subminute_pause_from_active_seconds(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        now = timezone.make_aware(datetime(2026, 7, 7, 12, 0, 30))
        session = WorkSession.objects.create(
            user=user,
            state=WorkSession.State.PAUSED,
            started_at=now - timedelta(seconds=30),
            paused_at=now - timedelta(seconds=15),
        )

        self.client.force_login(user)
        with patch('features.time_tracking.views.timezone.now', return_value=now):
            response = self.client.post(reverse('resume_timer'), {'next': '/'})

        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.inactive_seconds, 15)
        self.assertEqual(session.active_seconds(now), 15)

    def test_timer_status_returns_active_seconds_without_current_pause(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        now = timezone.make_aware(datetime(2026, 7, 7, 12, 1, 0))
        WorkSession.objects.create(
            user=user,
            state=WorkSession.State.PAUSED,
            started_at=now - timedelta(seconds=60),
            paused_at=now - timedelta(seconds=15),
        )

        self.client.force_login(user)
        with patch('features.time_tracking.models.timezone.now', return_value=now):
            response = self.client.get(reverse('timer_status'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['state'], WorkSession.State.PAUSED)
        self.assertEqual(response.json()['active_seconds'], 45)

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

    def test_stop_paused_timer_excludes_subminute_pause_from_entry(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        now = timezone.make_aware(datetime(2026, 7, 7, 12, 0, 30))
        WorkSession.objects.create(
            user=user,
            state=WorkSession.State.PAUSED,
            started_at=now - timedelta(seconds=30),
            paused_at=now - timedelta(seconds=15),
        )

        self.client.force_login(user)
        with patch('features.time_tracking.views.timezone.now', return_value=now):
            response = self.client.post(reverse('stop_timer'), {'next': '/'})

        self.assertEqual(response.status_code, 302)
        entry = TimeEntry.objects.get(user=user)
        self.assertEqual(entry.inactive_seconds, 15)
        self.assertEqual(entry.duration_seconds, 15)


class TimeAccountingTests(TestCase):
    def test_employee_can_edit_work_time_until_next_day(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        start = timezone.make_aware(datetime(2026, 7, 6, 9, 0))
        entry = TimeEntry.objects.create(
            user=user,
            start=start,
            end=start + timedelta(hours=2),
            editable_until=timezone.make_aware(datetime(2026, 7, 7, 23, 59, 59)),
        )

        self.client.force_login(user)
        with patch('features.time_tracking.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 7, 7, 20, 0))):
            self.assertTrue(entry.can_be_edited_by(user))
            response = self.client.get(reverse('edit_time_entry', args=[entry.id]))

        self.assertEqual(response.status_code, 200)

    def test_friday_work_time_can_be_edited_until_monday_end(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        friday = timezone.make_aware(datetime(2026, 7, 3, 9, 0))

        self.client.force_login(user)
        response = self.client.post(reverse('time_entries'), {
            'project': '',
            'task': '',
            'start': '2026-07-03T09:00',
            'end': '2026-07-03T11:00',
            'comment': '',
        })

        self.assertEqual(response.status_code, 302)
        entry = TimeEntry.objects.get(user=user)
        self.assertEqual(timezone.localtime(entry.editable_until).date(), date(2026, 7, 6))

        with patch('features.time_tracking.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 7, 6, 22, 0))):
            self.assertTrue(entry.can_be_edited_by(user))
        with patch('features.time_tracking.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 7, 7, 0, 1))):
            self.assertFalse(entry.can_be_edited_by(user))

    def test_management_can_edit_work_time_only_until_month_end(self):
        manager = User.objects.create_user(username='manager', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        start = timezone.make_aware(datetime(2026, 7, 6, 9, 0))
        entry = TimeEntry.objects.create(
            user=employee,
            start=start,
            end=start + timedelta(hours=2),
            editable_until=start,
        )

        with patch('features.time_tracking.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 7, 31, 20, 0))):
            self.assertTrue(entry.can_be_edited_by(manager))
        with patch('features.time_tracking.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 8, 1, 0, 1))):
            self.assertFalse(entry.can_be_edited_by(manager))

    def test_task_worklog_does_not_affect_employee_payroll(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        save_hourly_rate(user, {
            'amount': Decimal('30.50'),
            'currency': 'PLN',
            'valid_from': date(2026, 7, 1),
            'valid_to': None,
        }, user)
        project = Project.objects.create(name='Client project')
        column = BoardColumn.objects.create(project=project, name='Do zrobienia')
        task = Task.objects.create(project=project, column=column, title='Client task')
        start = timezone.make_aware(datetime(2026, 7, 6, 9, 0))
        TimeEntry.objects.create(
            user=user,
            project=project,
            start=start,
            end=start + timedelta(hours=2),
            editable_until=start + timedelta(days=1),
        )
        TaskWorklog.objects.create(task=task, user=user, date=date(2026, 7, 6), hours=Decimal('5.00'), visible_to_client=True)

        payroll = payroll_amount(user, list(TimeEntry.objects.filter(user=user)), date(2026, 7, 1), date(2026, 8, 1))

        self.assertEqual(payroll, Decimal('61.00'))

    def test_employee_can_edit_task_worklog_only_same_day(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Do zrobienia')
        task = Task.objects.create(project=project, column=column, title='Task')
        worklog = TaskWorklog.objects.create(task=task, user=user, date=date(2026, 7, 6), hours=Decimal('1.20'))

        with patch('features.tasks.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 7, 6, 23, 0))):
            self.assertTrue(worklog.can_be_edited_by(user))
        with patch('features.tasks.models.timezone.now', return_value=timezone.make_aware(datetime(2026, 7, 7, 0, 1))):
            self.assertFalse(worklog.can_be_edited_by(user))

    def test_time_entries_show_total_hours_for_selected_month(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        start = timezone.make_aware(datetime(2026, 7, 6, 9, 0))
        TimeEntry.objects.create(
            user=user,
            start=start,
            end=start + timedelta(hours=2),
            editable_until=start + timedelta(days=1),
        )
        TimeEntry.objects.create(
            user=user,
            start=start + timedelta(days=1),
            end=start + timedelta(days=1, hours=1, minutes=30),
            editable_until=start + timedelta(days=2),
        )

        self.client.force_login(user)
        response = self.client.get(reverse('time_entries'), {'month': '2026-07'})

        self.assertContains(response, 'Suma godzin')
        self.assertContains(response, '3,50h')

    def test_worklogs_filter_entries_and_task_choices_by_project(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        project_a = Project.objects.create(name='Projekt A')
        project_b = Project.objects.create(name='Projekt B')
        ProjectAssignment.objects.create(project=project_a, user=user)
        ProjectAssignment.objects.create(project=project_b, user=user)
        column_a = BoardColumn.objects.create(project=project_a, name='Do zrobienia')
        column_b = BoardColumn.objects.create(project=project_b, name='Do zrobienia')
        task_a = Task.objects.create(project=project_a, column=column_a, title='Zadanie A')
        task_b = Task.objects.create(project=project_b, column=column_b, title='Zadanie B')
        TaskWorklog.objects.create(task=task_a, user=user, date=date(2026, 7, 6), hours=Decimal('1.50'))
        TaskWorklog.objects.create(task=task_b, user=user, date=date(2026, 7, 6), hours=Decimal('2.00'))

        self.client.force_login(user)
        response = self.client.get(reverse('worklogs'), {'project': project_a.id})

        self.assertContains(response, 'Projekt A')
        self.assertContains(response, 'Zadanie A')
        self.assertContains(response, '1,50h')
        self.assertNotContains(response, 'Zadanie B')

    def test_time_accounting_pages_render_separate_tabs(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        time_response = self.client.get(reverse('time_entries'))
        worklog_response = self.client.get(reverse('worklogs'))

        self.assertEqual(time_response.status_code, 200)
        self.assertContains(time_response, 'Mój czas pracy')
        self.assertContains(time_response, 'Czas zadań projektowych')
        self.assertEqual(worklog_response.status_code, 200)
        self.assertContains(worklog_response, 'Czas zadań projektowych')
        self.assertNotContains(worklog_response, 'nie wchodzi do wynagrodzenia')
        self.assertNotContains(time_response, 'name="project"')

    def test_employee_report_contains_only_employee_summary_and_columns(self):
        user = User.objects.create_user(username='report-employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Twój raport pracy')
        self.assertContains(response, 'Czas pracy')
        self.assertContains(response, 'Czas przy zadaniach')
        self.assertNotContains(response, '<th>Pracownik</th>', html=True)
        self.assertNotContains(response, 'Podział pracowników')


class ExportPdfTests(TestCase):
    def test_management_export_without_user_is_project_report(self):
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

        self.assertContains(response, 'Raport projektu')
        self.assertContains(response, 'Podsumowanie projekt')

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
        column = BoardColumn.objects.create(project=project, name='Done', is_done_column=True)
        task = Task.objects.create(project=project, column=column, title='Visible task')
        TaskWorklog.objects.create(task=task, user=employee, hours='3.50', visible_to_client=True)

        self.client.force_login(client)
        response = self.client.get(reverse('reports'))

        self.assertContains(response, 'Client project')
        self.assertContains(response, '3,50h')

    def test_project_pdf_and_csv_include_rates_and_amounts(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee = User.objects.create_user(username='employee')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Client project', client_hourly_rate=Decimal('100.00'))
        column = BoardColumn.objects.create(project=project, name='Done', is_done_column=True)
        task = Task.objects.create(project=project, column=column, title='Priced task', labels='backend')
        ProjectLabelRate.objects.create(project=project, label='backend', hourly_rate=Decimal('220.00'))
        TaskWorklog.objects.create(task=task, user=employee, date=timezone.localdate(), hours=Decimal('2.00'), visible_to_client=True)

        self.client.force_login(manager)
        pdf_response = self.client.get(reverse('export_pdf'))
        csv_response = self.client.get(reverse('export_csv'))

        self.assertContains(pdf_response, '220,00 PLN/h')
        self.assertContains(pdf_response, '440,00 PLN')
        csv_content = csv_response.content.decode('utf-8')
        self.assertIn('Stawka', csv_content)
        self.assertIn('Kwota', csv_content)
        self.assertIn('220.00', csv_content)
        self.assertIn('440.00', csv_content)

    def test_management_pdf_uses_management_scope_label(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Client project')
        column = BoardColumn.objects.create(project=project, name='Done', is_done_column=True)
        task = Task.objects.create(project=project, column=column, title='Task')
        TaskWorklog.objects.create(task=task, user=manager, date=timezone.localdate(), hours=Decimal('1.00'))

        self.client.force_login(manager)
        response = self.client.get(reverse('export_pdf'), {'visibility': 'management'})

        self.assertContains(response, 'godziny widoczne dla managementu')
        self.assertNotContains(response, 'godziny widoczne dla klienta')
        self.assertContains(response, 'Zakres')

    def test_client_pdf_hides_scope_label(self):
        client = User.objects.create_user(username='client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        column = BoardColumn.objects.create(project=project, name='Done')
        task = Task.objects.create(project=project, column=column, title='Task')
        TaskWorklog.objects.create(task=task, user=client, date=timezone.localdate(), hours=Decimal('1.00'))

        self.client.force_login(client)
        response = self.client.get(reverse('export_pdf'), {'visibility': 'client', 'project': project.pk})

        self.assertNotContains(response, 'Zakres')
        self.assertNotContains(response, 'godziny widoczne dla klienta')


class EmployeePayrollRangeTests(TestCase):
    def test_management_can_filter_payroll_by_custom_date_range(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        save_hourly_rate(employee, {
            'amount': Decimal('100.00'),
            'currency': 'PLN',
            'valid_from': date(2026, 7, 1),
            'valid_to': None,
        }, manager)
        first_start = timezone.make_aware(datetime(2026, 7, 1, 9, 0))
        second_start = timezone.make_aware(datetime(2026, 7, 20, 9, 0))
        TimeEntry.objects.create(user=employee, start=first_start, end=first_start + timedelta(hours=2), editable_until=first_start)
        TimeEntry.objects.create(user=employee, start=second_start, end=second_start + timedelta(hours=3), editable_until=second_start)

        self.client.force_login(manager)
        response = self.client.get(reverse('employees'), {
            'date_from': '2026-07-01',
            'date_to': '2026-07-15',
        })

        self.assertContains(response, '2026-07-01 - 2026-07-15')
        self.assertContains(response, '2,00h')
        self.assertContains(response, '200,00 PLN')


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
        self.assertNotContains(response, 'przepracowane')
        self.assertContains(response, 'Deadline task')

    def test_calendar_week_view_shows_single_week_navigation(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()

        self.client.force_login(user)
        response = self.client.get(reverse('calendar'), {'view': 'week', 'week': '2026-07-14'})

        self.assertContains(response, 'Widok tygodniowy')
        self.assertContains(response, '2026-07-13 - 2026-07-19')
        self.assertContains(response, '?view=week&amp;week=2026-07-06')
        self.assertContains(response, '?view=week&amp;week=2026-07-20')
        self.assertContains(response, 'week-board')

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

    def test_employee_cannot_request_leave_in_the_past(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        yesterday = timezone.localdate() - timedelta(days=1)

        self.client.force_login(user)
        response = self.client.post(reverse('calendar'), {
            'form': 'leave_request',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'Urlop',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(LeaveRequest.objects.filter(user=user).exists())
        self.assertContains(response, 'Nie można brać wolnego w przeszłości.')

    def test_calendar_shows_leave_days_summary_without_weekends(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        LeaveRequest.objects.create(
            user=user,
            start_date=date(2026, 7, 13),
            end_date=date(2026, 7, 20),
            status=LeaveRequest.Status.APPROVED,
        )
        LeaveRequest.objects.create(
            user=user,
            start_date=date(2026, 7, 21),
            end_date=date(2026, 7, 21),
            status=LeaveRequest.Status.REJECTED,
        )

        self.client.force_login(user)
        response = self.client.get(reverse('calendar'), {'month': '2026-07'})

        self.assertContains(response, 'Wolne: 6 dni roboczych')

    def test_calendar_leave_summary_counts_only_unique_approved_workdays(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        LeaveRequest.objects.create(
            user=user,
            start_date=date(2026, 7, 13),
            end_date=date(2026, 7, 15),
            status=LeaveRequest.Status.APPROVED,
        )
        LeaveRequest.objects.create(
            user=user,
            start_date=date(2026, 7, 14),
            end_date=date(2026, 7, 16),
            status=LeaveRequest.Status.APPROVED,
        )
        LeaveRequest.objects.create(
            user=user,
            start_date=date(2026, 7, 17),
            end_date=date(2026, 7, 17),
            status=LeaveRequest.Status.PENDING,
        )

        self.client.force_login(user)
        response = self.client.get(reverse('calendar'), {'month': '2026-07'})

        self.assertContains(response, 'Wolne: 4 dni roboczych')
        self.assertContains(response, 'data-approved-leave="1"')

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

    def test_management_calendar_hides_rejected_leave_from_month_board(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee = User.objects.create_user(username='employee', first_name='Jan', last_name='Nowak', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        LeaveRequest.objects.create(
            user=employee,
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 20),
            status=LeaveRequest.Status.REJECTED,
            reviewed_by=manager,
            reviewed_at=timezone.now(),
            reason='Nie pasuje',
        )

        self.client.force_login(manager)
        response = self.client.get(reverse('calendar'), {'month': '2026-07'})

        self.assertContains(response, 'Odrzucony')
        self.assertContains(response, 'Nie pasuje')
        self.assertNotContains(response, 'note-leave rejected')

    def test_client_calendar_does_not_show_leave_request_form(self):
        client = User.objects.create_user(username='client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()

        self.client.force_login(client)
        response = self.client.get(reverse('calendar'))

        self.assertNotContains(response, 'Wyślij wniosek')
        self.assertNotContains(response, 'Moje wnioski')

    def test_employee_can_mark_rejected_leave_as_read_and_hide_it_from_calendar(self):
        user = User.objects.create_user(username='employee', password='pass')
        reviewer = User.objects.create_user(username='manager', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        reviewer.profile.role = UserProfile.Role.MANAGEMENT
        reviewer.profile.save()
        leave_request = LeaveRequest.objects.create(
            user=user,
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 22),
            status=LeaveRequest.Status.REJECTED,
            reviewed_by=reviewer,
            reviewed_at=timezone.now(),
        )

        self.client.force_login(user)
        response = self.client.get(reverse('calendar'), {'month': '2026-07'})
        self.assertContains(response, 'Oznacz jako przeczytane')

        mark_response = self.client.post(reverse('mark_leave_as_read', args=[leave_request.id]), {
            'next': f"{reverse('calendar')}?month=2026-07",
        })

        self.assertEqual(mark_response.status_code, 302)
        leave_request.refresh_from_db()
        self.assertIsNotNone(leave_request.read_at)

        refreshed = self.client.get(reverse('calendar'), {'month': '2026-07'})
        self.assertNotContains(refreshed, '20 lipca 2026 - 22 lipca 2026')
        self.assertNotContains(refreshed, 'Odrzucony')
        self.assertNotContains(refreshed, 'Oznacz jako przeczytane')

    def test_leave_requests_are_sorted_future_first_then_past(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        LeaveRequest.objects.create(user=user, start_date=date(2026, 7, 15), end_date=date(2026, 7, 15))
        LeaveRequest.objects.create(user=user, start_date=date(2026, 7, 5), end_date=date(2026, 7, 5))
        LeaveRequest.objects.create(user=user, start_date=date(2026, 7, 10), end_date=date(2026, 7, 10))

        self.client.force_login(user)
        with patch('features.planner.views.timezone.localdate', return_value=date(2026, 7, 10)):
            response = self.client.get(reverse('calendar'), {'month': '2026-07'})

        content = response.content.decode('utf-8')
        self.assertLess(content.index('10 lipca 2026 - 10 lipca 2026'), content.index('15 lipca 2026 - 15 lipca 2026'))
        self.assertLess(content.index('15 lipca 2026 - 15 lipca 2026'), content.index('5 lipca 2026 - 5 lipca 2026'))


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
    def test_new_columns_default_to_full_permissions_for_every_role(self):
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Lista', position=4)

        self.assertTrue(all(getattr(column, field_name) for field_name in BoardColumn.PERMISSION_FIELDS))

    def test_manager_can_star_and_color_task_card(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Lista')
        regular = Task.objects.create(project=project, column=column, title='Regular')
        starred = Task.objects.create(project=project, column=column, title='Starred')

        self.client.force_login(manager)
        star_response = self.client.post(reverse('update_task_card', args=[starred.id]), {'action': 'toggle_star'})
        color_response = self.client.post(reverse('update_task_card', args=[starred.id]), {'action': 'set_color', 'color': 'blue'})

        starred.refresh_from_db()
        self.assertEqual(star_response.status_code, 200)
        self.assertEqual(color_response.status_code, 200)
        self.assertTrue(starred.is_starred)
        self.assertEqual(starred.card_color, Task.CardColor.BLUE)
        self.assertEqual(list(column.tasks.values_list('id', flat=True)), [starred.id, regular.id])

    def test_user_without_edit_permission_cannot_change_task_card(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Lista')
        column.employee_can_edit_tasks = False
        column.save(update_fields=['employee_can_edit_tasks'])
        task = Task.objects.create(project=project, column=column, title='Task')

        self.client.force_login(employee)
        response = self.client.post(reverse('update_task_card', args=[task.id]), {'action': 'toggle_star'})

        self.assertEqual(response.status_code, 403)
        task.refresh_from_db()
        self.assertFalse(task.is_starred)

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

    def test_project_board_hides_project_field_and_uses_current_project(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)

        self.client.force_login(manager)
        page = self.client.get(reverse('kanban_project', args=[project.id]))
        response = self.client.post(reverse('kanban_project', args=[project.id]), {
            'column': column.id,
            'title': 'Task without explicit project',
            'description': 'Opis',
            'due_date': '',
            'priority': 'medium',
        })

        self.assertNotContains(page, 'name="project"')
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title='Task without explicit project')
        self.assertEqual(task.project, project)

    def test_employee_can_move_task_to_done_by_default(self):
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

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.column, done)

    def test_employee_can_choose_done_column_in_task_form_by_default(self):
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

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Task.objects.filter(title='Task for employee', column=done).exists())

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

    def test_client_can_move_task_between_columns_by_default(self):
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

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.column, done)

    def test_project_employee_without_edit_permission_cannot_rename_or_move_task(self):
        employee = User.objects.create_user(username='employee-no-edit', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Permission project')
        ProjectAssignment.objects.create(project=project, user=employee)
        source = BoardColumn.objects.create(
            project=project,
            name='Bez edycji',
            position=0,
            employee_can_view_column=True,
            employee_can_edit_tasks=False,
            employee_can_move_to=False,
            lead_can_move_to=True,
        )
        target = BoardColumn.objects.create(
            project=project,
            name='Docelowa',
            position=1,
            employee_can_view_column=True,
            employee_can_move_to=True,
            lead_can_move_to=True,
        )
        task = Task.objects.create(project=project, column=source, title='Stara nazwa')

        self.client.force_login(employee)
        edit_response = self.client.post(reverse('edit_task', args=[task.id]), {
            'title': 'Nowa nazwa',
            'description': '',
            'due_date': '',
            'priority': 'medium',
            'change_note': '',
        })
        move_response = self.client.post(reverse('move_task', args=[task.id]), {'column': target.id})

        task.refresh_from_db()
        self.assertEqual(edit_response.status_code, 403)
        self.assertEqual(move_response.status_code, 403)
        self.assertEqual(task.title, 'Stara nazwa')
        self.assertEqual(task.column, source)

    def test_client_can_edit_only_todo_tasks_and_leave_note(self):
        client = User.objects.create_user(username='client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        task = Task.objects.create(project=project, column=todo, title='Initial title', created_by=client)

        self.client.force_login(client)
        response = self.client.post(reverse('edit_task', args=[task.id]), {
            'title': 'Updated title',
            'description': 'Updated description',
            'due_date': '',
            'priority': 'medium',
            'change_note': 'Korekta opisu',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('edit_task', args=[task.id]))
        task.refresh_from_db()
        self.assertEqual(task.title, 'Updated title')
        self.assertTrue(TaskEditNote.objects.filter(task=task, user=client, content='Korekta opisu').exists())

    def test_employee_can_edit_in_progress_task_with_note(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Employee project')
        ProjectAssignment.objects.create(project=project, user=employee)
        doing = BoardColumn.objects.create(project=project, name='W trakcie', position=1)
        task = Task.objects.create(project=project, column=doing, title='Initial title', created_by=employee)

        self.client.force_login(employee)
        response = self.client.post(reverse('edit_task', args=[task.id]), {
            'title': 'Updated title',
            'description': 'Updated description',
            'due_date': '',
            'priority': 'high',
            'change_note': 'Zmieniono treść',
        })

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.priority, 'high')
        self.assertTrue(TaskEditNote.objects.filter(task=task, user=employee, content='Zmieniono treść').exists())

    def test_employee_can_edit_todo_task(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Employee project')
        ProjectAssignment.objects.create(project=project, user=employee)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        task = Task.objects.create(project=project, column=todo, title='Initial title', created_by=employee)

        self.client.force_login(employee)
        response = self.client.post(reverse('edit_task', args=[task.id]), {
            'title': 'Todo updated',
            'description': 'Updated description',
            'due_date': '',
            'priority': 'medium',
            'change_note': '',
        })

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.title, 'Todo updated')

    def test_employee_non_owner_can_edit_task_fields_by_default(self):
        owner = User.objects.create_user(username='owner', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        owner.profile.role = UserProfile.Role.EMPLOYEE
        owner.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Employee project')
        ProjectAssignment.objects.create(project=project, user=owner)
        ProjectAssignment.objects.create(project=project, user=employee)
        doing = BoardColumn.objects.create(project=project, name='W trakcie', position=1)
        task = Task.objects.create(project=project, column=doing, title='Initial title', priority='medium', created_by=owner)

        self.client.force_login(employee)
        response = self.client.post(reverse('edit_task', args=[task.id]), {
            'title': 'Changed by non owner',
            'description': 'Changed description',
            'due_date': '',
            'priority': 'high',
            'change_note': 'Tylko notatka',
        })

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.title, 'Changed by non owner')
        self.assertEqual(task.priority, 'high')
        self.assertTrue(TaskEditNote.objects.filter(task=task, user=employee, content='Tylko notatka').exists())

        edit_page = self.client.get(reverse('edit_task', args=[task.id]))
        self.assertNotContains(edit_page, 'readonly-field')
        self.assertContains(edit_page, 'Changed by non owner')

    def test_employee_can_edit_review_task_by_default(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Employee project')
        ProjectAssignment.objects.create(project=project, user=employee)
        review = BoardColumn.objects.create(project=project, name='Review', position=2)
        task = Task.objects.create(project=project, column=review, title='Review task')

        self.client.force_login(employee)
        response = self.client.get(reverse('edit_task', args=[task.id]))

        self.assertEqual(response.status_code, 200)

    def test_lead_can_edit_review_task_and_manager_can_delete_done_task(self):
        lead = User.objects.create_user(username='lead', password='pass')
        lead.profile.role = UserProfile.Role.EMPLOYEE
        lead.profile.save()
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=lead, project_role=ProjectAssignment.ProjectRole.LEAD)
        review = BoardColumn.objects.create(project=project, name='Review', position=2)
        done = BoardColumn.objects.create(project=project, name='Zakończone', position=3)
        review_task = Task.objects.create(project=project, column=review, title='Review task', created_by=lead)
        done_task = Task.objects.create(project=project, column=done, title='Done task')

        self.client.force_login(lead)
        response = self.client.post(reverse('edit_task', args=[review_task.id]), {
            'title': 'Review task updated',
            'description': 'Opis',
            'due_date': '',
            'priority': 'medium',
            'change_note': 'Lead poprawił review',
        })

        self.assertEqual(response.status_code, 302)
        review_task.refresh_from_db()
        self.assertEqual(review_task.title, 'Review task updated')

        self.client.force_login(manager)
        delete_response = self.client.post(reverse('delete_task', args=[done_task.id]))

        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Task.objects.filter(pk=done_task.pk).exists())

    def test_employee_can_delete_project_tasks_by_default(self):
        employee = User.objects.create_user(username='employee', password='pass')
        other = User.objects.create_user(username='other', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        other.profile.role = UserProfile.Role.EMPLOYEE
        other.profile.save()
        project = Project.objects.create(name='Employee project')
        ProjectAssignment.objects.create(project=project, user=employee)
        ProjectAssignment.objects.create(project=project, user=other)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        own_task = Task.objects.create(project=project, column=todo, title='Own task', created_by=employee)
        other_task = Task.objects.create(project=project, column=todo, title='Other task', created_by=other)

        self.client.force_login(employee)
        forbidden = self.client.post(reverse('delete_task', args=[other_task.id]))
        allowed = self.client.post(reverse('delete_task', args=[own_task.id]))

        self.assertEqual(forbidden.status_code, 302)
        self.assertEqual(allowed.status_code, 302)
        self.assertFalse(Task.objects.filter(pk=other_task.pk).exists())
        self.assertFalse(Task.objects.filter(pk=own_task.pk).exists())

    def test_client_can_delete_project_tasks_by_default(self):
        client = User.objects.create_user(username='client', password='pass')
        other_client = User.objects.create_user(username='other_client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        other_client.profile.role = UserProfile.Role.CLIENT
        other_client.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        ProjectAssignment.objects.create(project=project, user=other_client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        own_task = Task.objects.create(project=project, column=todo, title='Own client task', created_by=client)
        other_task = Task.objects.create(project=project, column=todo, title='Other client task', created_by=other_client)

        self.client.force_login(client)
        forbidden = self.client.post(reverse('delete_task', args=[other_task.id]))
        allowed = self.client.post(reverse('delete_task', args=[own_task.id]))

        self.assertEqual(forbidden.status_code, 302)
        self.assertEqual(allowed.status_code, 302)
        self.assertFalse(Task.objects.filter(pk=other_task.pk).exists())
        self.assertFalse(Task.objects.filter(pk=own_task.pk).exists())

    def test_management_can_add_board_column(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)

        self.client.force_login(manager)
        response = self.client.post(reverse('kanban_project', args=[project.id]), {
            'form': 'board_column',
            'name': 'Blocked',
        })

        self.assertEqual(response.status_code, 302)
        created_column = BoardColumn.objects.get(project=project, name='Blocked')
        self.assertTrue(all(getattr(created_column, field_name) for field_name in BoardColumn.PERMISSION_FIELDS))

    def test_employee_can_see_and_add_the_last_board_column(self):
        employee = User.objects.create_user(username='employee-board-column', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=employee)
        BoardColumn.objects.create(project=project, name='Pierwsza', position=0)

        self.client.force_login(employee)
        page = self.client.get(reverse('kanban_project', args=[project.id]))
        response = self.client.post(reverse('kanban_project', args=[project.id]), {
            'form': 'board_column',
            'name': 'Kolejna',
        })

        self.assertContains(page, 'Dodaj kolejną kolumnę')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(BoardColumn.objects.filter(project=project, name='Kolejna').exists())

    def test_user_can_choose_default_project_for_tasks(self):
        employee = User.objects.create_user(username='employee-default-project', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        first_project = Project.objects.create(name='A project')
        preferred_project = Project.objects.create(name='B project')
        ProjectAssignment.objects.create(project=first_project, user=employee)
        ProjectAssignment.objects.create(project=preferred_project, user=employee)

        self.client.force_login(employee)
        set_response = self.client.post(reverse('set_default_tasks_project', args=[preferred_project.id]))
        projects_page = self.client.get(reverse('projects'))
        board_response = self.client.get(reverse('kanban'))

        self.assertEqual(set_response.status_code, 302)
        employee.profile.refresh_from_db()
        self.assertEqual(employee.profile.default_tasks_project, preferred_project)
        self.assertContains(projects_page, 'Domyślny')
        self.assertRedirects(board_response, reverse('kanban_project', args=[preferred_project.id]))

    def test_only_management_can_open_column_permission_settings(self):
        employee = User.objects.create_user(username='employee-column-settings', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Kolumna', position=0)

        self.client.force_login(employee)
        board = self.client.get(reverse('kanban_project', args=[project.id]))
        response = self.client.post(reverse('update_column', args=[column.id]), {
            'name': 'Zmieniona',
            'client_can_edit_tasks': '',
        })

        self.assertNotContains(board, f'edit-column-{column.id}')
        self.assertEqual(response.status_code, 403)
        column.refresh_from_db()
        self.assertEqual(column.name, 'Kolumna')
        self.assertTrue(column.client_can_edit_tasks)

    def test_project_can_have_only_one_done_column(self):
        manager = User.objects.create_user(username='manager-one-done', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        first = BoardColumn.objects.create(project=project, name='Gotowe', position=0, is_done_column=True)
        second = BoardColumn.objects.create(project=project, name='Inna', position=1)

        self.client.force_login(manager)
        response = self.client.post(reverse('update_column', args=[second.id]), {
            'name': 'Inna',
            'is_done_column': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tylko jedna kolumna w projekcie może być oznaczona jako zakończona.')
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_done_column)
        self.assertFalse(second.is_done_column)

    def test_management_can_update_board_column_settings(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)

        self.client.force_login(manager)
        response = self.client.post(reverse('update_column', args=[column.id]), {
            'name': 'Backlog klienta',
            'is_done_column': 'on',
            'employee_can_move_to': 'on',
            'employee_can_edit_tasks': 'on',
            'lead_can_move_to': 'on',
        })

        self.assertEqual(response.status_code, 302)
        column.refresh_from_db()
        self.assertEqual(column.name, 'Backlog klienta')
        self.assertTrue(column.is_done_column)
        self.assertTrue(column.employee_can_move_to)
        self.assertFalse(column.client_can_edit_tasks)

    def test_management_can_open_board_column_settings_page(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)

        self.client.force_login(manager)
        response = self.client.get(reverse('update_column', args=[column.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="name"')
        self.assertContains(response, 'name="is_done_column"')
        self.assertContains(response, 'name="client_can_move_to"')
        self.assertContains(response, 'name="employee_can_edit_tasks"')
        self.assertContains(response, 'name="lead_can_delete_tasks"')

    def test_client_progress_uses_done_column_flag_not_column_name(self):
        client = User.objects.create_user(username='client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        done = BoardColumn.objects.create(project=project, name='Zrobione', position=1, is_done_column=True)
        Task.objects.create(project=project, column=todo, title='Open task')
        Task.objects.create(project=project, column=done, title='Finished task')

        self.client.force_login(client)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Zakończone')
        self.assertContains(response, '1 / 2')

    def test_client_dashboard_can_switch_project_summary(self):
        client = User.objects.create_user(username='client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        first_project = Project.objects.create(name='First project', client=client)
        second_project = Project.objects.create(name='Second project', client=client)
        first_column = BoardColumn.objects.create(project=first_project, name='Start', position=0)
        second_column = BoardColumn.objects.create(project=second_project, name='Done', position=0, is_done_column=True)
        Task.objects.create(project=first_project, column=first_column, title='First task')
        Task.objects.create(project=second_project, column=second_column, title='Second task')

        self.client.force_login(client)
        response = self.client.get(reverse('dashboard'), {'project': second_project.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Podsumowanie łączone')
        self.assertContains(response, 'Podsumowanie projektu')
        self.assertContains(response, f'?project={second_project.id}')
        self.assertContains(response, 'Second task')
        self.assertNotContains(response, 'First task</strong>')

    def test_management_can_allow_employee_to_move_to_custom_column(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=employee)
        todo = BoardColumn.objects.create(project=project, name='Start', position=0, employee_can_move_to=True, employee_can_edit_tasks=True)
        custom = BoardColumn.objects.create(project=project, name='QA', position=1)
        task = Task.objects.create(project=project, column=todo, title='Task for employee')

        self.client.force_login(manager)
        self.client.post(reverse('update_column', args=[custom.id]), {
            'name': 'QA',
            'employee_can_view_column': 'on',
            'employee_can_move_to': 'on',
            'employee_can_edit_tasks': 'on',
            'lead_can_view_column': 'on',
            'lead_can_move_to': 'on',
            'lead_can_edit_tasks': 'on',
        })

        self.client.force_login(employee)
        response = self.client.post(reverse('move_task', args=[task.id]), {'column': custom.id})

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.column, custom)

    def test_kanban_does_not_recreate_default_columns_after_customization(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        BoardColumn.objects.create(project=project, name='Custom only', position=0)

        self.client.force_login(manager)
        response = self.client.get(reverse('kanban_project', args=[project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(project.columns.values_list('name', flat=True)), ['Custom only'])

    def test_management_can_delete_empty_board_column(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        first = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        second = BoardColumn.objects.create(project=project, name='Extra', position=1)

        self.client.force_login(manager)
        response = self.client.post(reverse('delete_column', args=[second.id]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(BoardColumn.objects.filter(pk=first.pk, position=0).exists())
        self.assertFalse(BoardColumn.objects.filter(pk=second.pk).exists())

    def test_management_board_renders_add_column_toggle_and_hidden_delete_form(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        Task.objects.create(project=project, column=column, title='Task in column')

        self.client.force_login(manager)
        response = self.client.get(reverse('kanban_project', args=[project.id]))

        self.assertContains(response, 'add-column-toggle')
        self.assertContains(response, 'kanban-modal is-hidden')
        self.assertContains(response, 'delete-column-form is-hidden')

    def test_management_cannot_delete_column_with_tasks(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        BoardColumn.objects.create(project=project, name='Extra', position=1)
        Task.objects.create(project=project, column=column, title='Blocked task')

        self.client.force_login(manager)
        response = self.client.post(reverse('delete_column', args=[column.id]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(BoardColumn.objects.filter(pk=column.pk).exists())

    def test_management_can_create_and_render_task_labels(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)

        self.client.force_login(manager)
        response = self.client.post(reverse('kanban_project', args=[project.id]), {
            'project': project.id,
            'column': column.id,
            'title': 'Task with labels',
            'description': 'Opis',
            'due_date': '',
            'priority': 'medium',
            'labels': 'pilne, backend',
        })

        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title='Task with labels')
        self.assertEqual(task.labels, 'pilne, backend')
        board = self.client.get(reverse('kanban_project', args=[project.id]))
        self.assertContains(board, 'pilne')
        self.assertContains(board, 'backend')

    def test_employee_and_client_can_edit_labels_by_default(self):
        employee = User.objects.create_user(username='employee', password='pass')
        client = User.objects.create_user(username='client', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Project', client=client)
        ProjectAssignment.objects.create(project=project, user=employee)
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        doing = BoardColumn.objects.create(project=project, name='W trakcie', position=1)
        todo = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        assigned_task = Task.objects.create(project=project, column=doing, title='Assigned task', assignee=employee)
        client_task = Task.objects.create(project=project, column=todo, title='Client task', created_by=client)

        self.client.force_login(employee)
        response = self.client.post(reverse('edit_task', args=[assigned_task.id]), {
            'title': 'Assigned task',
            'description': '',
            'due_date': '',
            'priority': 'medium',
            'labels': 'frontend',
            'change_note': '',
        })
        assigned_task.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(assigned_task.labels, 'frontend')

        self.client.force_login(client)
        edit_page = self.client.get(reverse('edit_task', args=[client_task.id]))

        self.assertContains(edit_page, 'data-label-transfer')

    def test_creating_assigned_task_sends_notification_to_assignee(self):
        manager = User.objects.create_user(username='manager', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)

        self.client.force_login(manager)
        response = self.client.post(reverse('kanban_project', args=[project.id]), {
            'project': project.id,
            'column': column.id,
            'title': 'New assigned task',
            'description': '',
            'due_date': '',
            'priority': 'medium',
            'labels': '',
            'assignee': employee.id,
        })

        self.assertEqual(response.status_code, 302)
        notification = Notification.objects.get(user=employee)
        self.assertEqual(notification.kind, 'task')
        self.assertIn('New assigned task', notification.content)
        self.assertIn('/edit/', notification.url)

    def test_task_note_sends_notification_to_assignee(self):
        manager = User.objects.create_user(username='manager', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Do zrobienia', position=0)
        task = Task.objects.create(project=project, column=column, title='Task', assignee=employee)

        self.client.force_login(manager)
        response = self.client.post(reverse('edit_task', args=[task.id]), {
            'title': 'Task',
            'description': '',
            'due_date': '',
            'priority': 'medium',
            'labels': '',
            'assignee': employee.id,
            'change_note': 'Please check details.',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(TaskEditNote.objects.filter(task=task, content='Please check details.').exists())
        self.assertTrue(Notification.objects.filter(user=employee, kind='task_note').exists())

    def test_leave_request_notifies_management_and_status_notifies_employee(self):
        manager = User.objects.create_user(username='manager', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        start = timezone.localdate() + timedelta(days=10)
        end = start + timedelta(days=1)

        self.client.force_login(employee)
        response = self.client.post(reverse('calendar'), {
            'form': 'leave_request',
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'reason': 'Urlop',
        })

        self.assertEqual(response.status_code, 302)
        leave_request = LeaveRequest.objects.get(user=employee)
        self.assertTrue(Notification.objects.filter(user=manager, kind='leave').exists())

        self.client.force_login(manager)
        response = self.client.post(reverse('update_leave_status', args=[leave_request.id]), {
            'status': LeaveRequest.Status.APPROVED,
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Notification.objects.filter(user=employee, kind='leave', title='Status wniosku o wolne').exists())

    def test_notifications_can_be_marked_as_read(self):
        user = User.objects.create_user(username='employee', password='pass')
        user.profile.role = UserProfile.Role.EMPLOYEE
        user.profile.save()
        first = Notification.objects.create(user=user, title='One', content='First')
        Notification.objects.create(user=user, title='Two', content='Second')

        self.client.force_login(user)
        response = self.client.post(reverse('mark_notification_read', args=[first.id]), {'next': reverse('notifications')})

        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        self.assertTrue(first.is_read)

        response = self.client.post(reverse('mark_all_notifications_read'), {'next': reverse('notifications')})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Notification.objects.filter(user=user, is_read=False).exists())

    def test_client_gets_notification_for_new_task_in_first_column(self):
        manager = User.objects.create_user(username='manager', password='pass')
        client = User.objects.create_user(username='client', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        column = BoardColumn.objects.create(project=project, name='Start', position=0)

        self.client.force_login(manager)
        response = self.client.post(reverse('kanban_project', args=[project.id]), {
            'project': project.id,
            'column': column.id,
            'title': 'Client visible task',
            'description': '',
            'due_date': '',
            'priority': 'medium',
            'labels': '',
            'assignee': '',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Notification.objects.filter(user=client, kind='client_task', content__contains='Client visible task').exists())

    def test_client_gets_note_notification_only_for_task_in_first_column(self):
        manager = User.objects.create_user(username='manager', password='pass')
        client = User.objects.create_user(username='client', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        first = BoardColumn.objects.create(project=project, name='Start', position=0)
        second = BoardColumn.objects.create(project=project, name='Work', position=1)
        first_task = Task.objects.create(project=project, column=first, title='First task')
        second_task = Task.objects.create(project=project, column=second, title='Second task')

        self.client.force_login(manager)
        response = self.client.post(reverse('edit_task', args=[first_task.id]), {
            'title': 'First task',
            'description': '',
            'due_date': '',
            'priority': 'medium',
            'labels': '',
            'assignee': '',
            'change_note': 'Client should see this.',
        })
        self.assertEqual(response.status_code, 302)

        response = self.client.post(reverse('edit_task', args=[second_task.id]), {
            'title': 'Second task',
            'description': '',
            'due_date': '',
            'priority': 'medium',
            'labels': '',
            'assignee': '',
            'change_note': 'Client should not see this.',
        })
        self.assertEqual(response.status_code, 302)

        self.assertTrue(Notification.objects.filter(user=client, kind='client_note', content__contains='First task').exists())
        self.assertFalse(Notification.objects.filter(user=client, kind='client_note', content__contains='Second task').exists())

    def test_client_gets_notification_when_task_moves_to_last_column(self):
        employee = User.objects.create_user(username='employee', password='pass')
        client = User.objects.create_user(username='client', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        ProjectAssignment.objects.create(project=project, user=employee)
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        start = BoardColumn.objects.create(project=project, name='Start', position=0)
        done = BoardColumn.objects.create(project=project, name='Done', position=1, employee_can_move_to=True, notify_client_on_move_to=True)
        task = Task.objects.create(project=project, column=start, title='Finish me', assignee=employee)

        self.client.force_login(employee)
        response = self.client.post(reverse('move_task', args=[task.id]), {'column': done.id})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Notification.objects.filter(user=client, kind='client_task', content__contains='Finish me').exists())

    def test_column_notification_settings_control_move_notifications(self):
        employee = User.objects.create_user(username='employee', password='pass')
        client = User.objects.create_user(username='client', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        ProjectAssignment.objects.create(project=project, user=employee)
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        start = BoardColumn.objects.create(project=project, name='Start', position=0)
        review = BoardColumn.objects.create(
            project=project,
            name='Review',
            position=1,
            employee_can_move_to=True,
            notify_client_on_move_to=True,
            notify_assignee_on_move_to=False,
        )
        task = Task.objects.create(project=project, column=start, title='Review task', assignee=employee)

        self.client.force_login(employee)
        response = self.client.post(reverse('move_task', args=[task.id]), {'column': review.id})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Notification.objects.filter(user=client, kind='client_task', content__contains='Review task').exists())
        self.assertFalse(Notification.objects.filter(user=employee, kind='task', content__contains='Review task').exists())

    def test_daily_reminders_create_deadline_and_leave_notifications(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Start', position=0)
        tomorrow = timezone.localdate() + timedelta(days=1)
        Task.objects.create(project=project, column=column, title='Due tomorrow', assignee=employee, due_date=tomorrow)
        LeaveRequest.objects.create(user=employee, start_date=tomorrow, end_date=tomorrow, status=LeaveRequest.Status.APPROVED)

        self.client.force_login(employee)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Notification.objects.filter(user=employee, kind='task_deadline', content__contains='Due tomorrow').exists())
        self.assertTrue(Notification.objects.filter(user=employee, kind='leave_reminder').exists())

    def test_client_report_hides_visibility_column(self):
        client = User.objects.create_user(username='client', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Client project', client=client)
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        column = BoardColumn.objects.create(project=project, name='Done', position=0, is_done_column=True)
        task = Task.objects.create(project=project, column=column, title='Visible task')
        TaskWorklog.objects.create(task=task, user=employee, date=timezone.localdate(), hours=Decimal('2.00'), visible_to_client=True)

        self.client.force_login(client)
        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Raport klienta')
        self.assertNotContains(response, '<th>Klient</th>')
        self.assertNotContains(response, '<th>Pracownik</th>')
        self.assertNotContains(response, 'employee')
        self.assertNotContains(response, '<td>widzi</td>')

    def test_client_report_uses_first_matching_label_rate(self):
        client = User.objects.create_user(username='client', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Client project', client=client, client_hourly_rate=Decimal('100.00'))
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        column = BoardColumn.objects.create(project=project, name='Done', position=0, is_done_column=True)
        task = Task.objects.create(project=project, column=column, title='Priced task', labels='backend, frontend')
        ProjectLabelRate.objects.create(project=project, label='backend', hourly_rate=Decimal('220.00'))
        ProjectLabelRate.objects.create(project=project, label='frontend', hourly_rate=Decimal('190.00'))
        TaskWorklog.objects.create(task=task, user=employee, date=timezone.localdate(), hours=Decimal('2.00'), visible_to_client=True)

        self.client.force_login(client)
        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '220,00 PLN/h')
        self.assertContains(response, '440,00 PLN')
        self.assertContains(response, 'backend')

    def test_client_report_falls_back_to_project_rate_without_label_rate(self):
        client = User.objects.create_user(username='client', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Client project', client=client, client_hourly_rate=Decimal('150.00'))
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        column = BoardColumn.objects.create(project=project, name='Done', position=0, is_done_column=True)
        task = Task.objects.create(project=project, column=column, title='Default priced task', labels='support')
        TaskWorklog.objects.create(task=task, user=employee, date=timezone.localdate(), hours=Decimal('3.00'), visible_to_client=True)

        self.client.force_login(client)
        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '150,00 PLN/h')
        self.assertContains(response, '450,00 PLN')

    def test_client_projects_show_project_and_label_rates(self):
        client = User.objects.create_user(username='client', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client, client_hourly_rate=Decimal('150.00'), client_rate_currency='PLN')
        ProjectAssignment.objects.create(project=project, user=client, project_role=ProjectAssignment.ProjectRole.CLIENT)
        ProjectLabelRate.objects.create(project=project, label='backend', hourly_rate=Decimal('220.00'), currency='PLN')

        self.client.force_login(client)
        list_response = self.client.get(reverse('projects'))
        detail_response = self.client.get(reverse('project_detail', args=[project.id]))

        self.assertContains(list_response, 'Stawka podstawowa')
        self.assertContains(list_response, '150,00 PLN/h')
        self.assertContains(detail_response, 'Stawki projektu')
        self.assertContains(detail_response, 'Stawka podstawowa')
        self.assertContains(detail_response, 'backend')
        self.assertContains(detail_response, '220,00 PLN/h')
        self.assertNotContains(detail_response, 'frontend')

    def test_management_can_add_and_update_project_label_rate(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')

        self.client.force_login(manager)
        response = self.client.post(reverse('project_detail', args=[project.id]), {
            'form': 'label_rate',
            'label': 'Backend',
            'hourly_rate': '220,50',
            'currency': 'pln',
        })

        self.assertEqual(response.status_code, 302)
        rate = ProjectLabelRate.objects.get(project=project)
        self.assertEqual(rate.label, 'backend')
        self.assertEqual(rate.hourly_rate, Decimal('220.50'))
        self.assertEqual(rate.currency, 'PLN')

        page = self.client.get(reverse('project_detail', args=[project.id]))
        self.assertContains(page, 'backend')
        self.assertContains(page, '220,50 PLN/h')

        response = self.client.post(reverse('project_detail', args=[project.id]), {
            'form': 'label_rate',
            'label': 'backend',
            'hourly_rate': '250.00',
            'currency': 'PLN',
        })

        self.assertEqual(response.status_code, 302)
        rate.refresh_from_db()
        self.assertEqual(rate.hourly_rate, Decimal('250.00'))
        self.assertEqual(ProjectLabelRate.objects.filter(project=project, label='backend').count(), 1)

    def test_kanban_shows_project_label_rate_suggestions_and_card_rates(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project', client_hourly_rate=Decimal('100.00'))
        column = BoardColumn.objects.create(project=project, name='Start', position=0)
        ProjectLabelRate.objects.create(project=project, label='backend', hourly_rate=Decimal('220.00'))
        Task.objects.create(project=project, column=column, title='Priced task', labels='backend, new-label')

        self.client.force_login(manager)
        response = self.client.get(reverse('kanban_project', args=[project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-label-transfer')
        self.assertContains(response, 'data-label-value="backend"')
        self.assertContains(response, 'backend')
        self.assertContains(response, '220,00 PLN/h')
        self.assertNotContains(response, 'Stawka: 220,00 PLN/h')

    def test_management_can_save_multiple_task_labels(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Start', position=0)
        ProjectLabelRate.objects.create(project=project, label='backend', hourly_rate=Decimal('220.00'))
        task = Task.objects.create(project=project, column=column, title='Task')

        self.client.force_login(manager)
        response = self.client.post(reverse('edit_task', args=[task.id]), {
            'title': 'Task',
            'description': '',
            'due_date': '',
            'priority': 'medium',
            'labels': 'backend, frontend, qa',
            'change_note': '',
        })

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.labels, 'backend, frontend, qa')

    def test_kanban_card_shows_hidden_label_count(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Project')
        column = BoardColumn.objects.create(project=project, name='Start', position=0)
        Task.objects.create(project=project, column=column, title='Task', labels='backend, frontend, qa, design, test')

        self.client.force_login(manager)
        response = self.client.get(reverse('kanban_project', args=[project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'backend')
        self.assertContains(response, 'frontend')
        self.assertContains(response, 'label-more-chip')
        self.assertContains(response, '+3')

    def test_kanban_hides_task_rates_from_employee(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Project', client_hourly_rate=Decimal('100.00'))
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Start', position=0)
        ProjectLabelRate.objects.create(project=project, label='backend', hourly_rate=Decimal('220.00'))
        Task.objects.create(project=project, column=column, title='Priced task', labels='backend')

        self.client.force_login(employee)
        response = self.client.get(reverse('kanban_project', args=[project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'backend')
        self.assertNotContains(response, '220,00 PLN/h')
        self.assertNotContains(response, 'Stawka:')

    def test_kanban_preview_can_add_task_note(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Start', position=0)
        task = Task.objects.create(project=project, column=column, title='Task with note', assignee=employee)

        self.client.force_login(employee)
        response = self.client.post(reverse('add_task_note', args=[task.id]), {'content': 'Nowa notatka z popupu'})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(TaskEditNote.objects.filter(task=task, user=employee, content='Nowa notatka z popupu').exists())

    def test_kanban_preview_can_add_task_attachment(self):
        employee = User.objects.create_user(username='employee', password='pass')
        outsider = User.objects.create_user(username='outsider', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        outsider.profile.role = UserProfile.Role.EMPLOYEE
        outsider.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Start', position=0)
        task = Task.objects.create(project=project, column=column, title='Task with attachment', assignee=employee)

        self.client.force_login(employee)
        response = self.client.post(reverse('add_task_attachment', args=[task.id]), {
            'name': 'Spec',
            'file': SimpleUploadedFile('spec.txt', b'abc', content_type='text/plain'),
        })

        self.assertEqual(response.status_code, 302)
        attachment = Attachment.objects.get(task=task)
        self.assertEqual(attachment.name, 'Spec')
        self.assertIsNotNone(attachment.document)
        self.assertEqual(attachment.document.name, 'Spec')
        self.assertTrue(attachment.document.file.name.endswith('.txt'))
        self.assertTrue(DocumentItem.objects.filter(name='Spec', owner=employee).exists())
        self.assertIn(attachment.document, DocumentItem.visible_to(employee))
        self.assertNotIn(attachment.document, DocumentItem.visible_to(outsider))
        self.assertFalse(attachment.document.can_edit(employee))
        self.assertFalse(attachment.document.can_manage(employee))

        rename_response = self.client.post(reverse('documents'), {
            'form': 'rename',
            'item': attachment.document.id,
            'name': 'Changed spec',
        })
        move_response = self.client.post(reverse('documents'), {
            'form': 'move',
            'item': attachment.document.id,
            'target_parent': '',
        })

        attachment.document.refresh_from_db()
        self.assertEqual(rename_response.status_code, 403)
        self.assertEqual(move_response.status_code, 403)
        self.assertEqual(attachment.document.name, 'Spec')

    def test_kanban_preview_rejects_disallowed_attachment_extension(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Start', position=0)
        task = Task.objects.create(project=project, column=column, title='Task with attachment', assignee=employee)

        self.client.force_login(employee)
        response = self.client.post(reverse('add_task_attachment', args=[task.id]), {
            'name': 'Setup',
            'file': SimpleUploadedFile('setup.exe', b'abc', content_type='application/octet-stream'),
        }, follow=True)

        self.assertContains(response, 'Nie mozna dodac pliku z rozszerzeniem .exe')
        self.assertFalse(Attachment.objects.filter(task=task).exists())
        self.assertFalse(DocumentItem.objects.filter(name='Setup', owner=employee).exists())

    def test_kanban_preview_can_link_existing_document(self):
        employee = User.objects.create_user(username='employee', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Project')
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Start', position=0)
        task = Task.objects.create(project=project, column=column, title='Task with document', assignee=employee)
        document = DocumentItem.objects.create(owner=employee, name='Brief', kind=DocumentItem.Kind.DOCUMENT, content='Opis')

        self.client.force_login(employee)
        response = self.client.post(reverse('link_task_document', args=[task.id]), {'document': document.id})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Attachment.objects.filter(task=task, document=document, name='Brief').exists())
        document.refresh_from_db()
        self.assertFalse(document.can_edit(employee))
        self.assertFalse(document.can_manage(employee))

    def test_management_report_defaults_to_client_visible_scope(self):
        manager = User.objects.create_user(username='manager', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        client = User.objects.create_user(username='client', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client, client_hourly_rate=Decimal('100.00'))
        column = BoardColumn.objects.create(project=project, name='Done', position=0, is_done_column=True)
        priced_task = Task.objects.create(project=project, column=column, title='Priced task', labels='backend')
        hidden_task = Task.objects.create(project=project, column=column, title='Hidden task')
        ProjectLabelRate.objects.create(project=project, label='backend', hourly_rate=Decimal('220.00'))
        TaskWorklog.objects.create(task=priced_task, user=employee, date=timezone.localdate(), hours=Decimal('2.00'), visible_to_client=True)
        TaskWorklog.objects.create(task=hidden_task, user=employee, date=timezone.localdate(), hours=Decimal('3.00'), visible_to_client=False)

        self.client.force_login(manager)
        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Godziny widoczne dla klienta')
        self.assertContains(response, '2,00h')
        self.assertContains(response, 'Godziny klienta')
        self.assertContains(response, '2,00h')
        self.assertContains(response, 'Kwota klienta')
        self.assertContains(response, '440,00 PLN')
        self.assertContains(response, '220,00 PLN/h')
        self.assertNotContains(response, '300,00 PLN')
        self.assertNotContains(response, 'ukryte')

    def test_management_report_can_switch_to_management_scope(self):
        manager = User.objects.create_user(username='manager', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        client = User.objects.create_user(username='client', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        project = Project.objects.create(name='Client project', client=client, client_hourly_rate=Decimal('100.00'))
        column = BoardColumn.objects.create(project=project, name='Done', position=0, is_done_column=True)
        priced_task = Task.objects.create(project=project, column=column, title='Priced task', labels='backend')
        hidden_task = Task.objects.create(project=project, column=column, title='Hidden task')
        ProjectLabelRate.objects.create(project=project, label='backend', hourly_rate=Decimal('220.00'))
        TaskWorklog.objects.create(task=priced_task, user=employee, date=timezone.localdate(), hours=Decimal('2.00'), visible_to_client=True)
        TaskWorklog.objects.create(task=hidden_task, user=employee, date=timezone.localdate(), hours=Decimal('3.00'), visible_to_client=False)

        self.client.force_login(manager)
        response = self.client.get(reverse('reports'), {'visibility': 'management'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Zakres raportu managementu')
        self.assertContains(response, 'Godziny łączne')
        self.assertContains(response, '5,00h')
        self.assertContains(response, 'Godziny klienta')
        self.assertContains(response, '2,00h')
        self.assertContains(response, 'Kwota wg stawek')
        self.assertContains(response, '740,00 PLN')
        self.assertContains(response, '300,00 PLN')
        self.assertContains(response, 'ukryte')

    def test_selected_project_report_uses_single_project_copy(self):
        manager = User.objects.create_user(username='manager', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        project = Project.objects.create(name='Solo project')
        column = BoardColumn.objects.create(project=project, name='Done', position=0, is_done_column=True)
        task = Task.objects.create(project=project, column=column, title='Task')
        TaskWorklog.objects.create(task=task, user=manager, date=timezone.localdate(), hours=Decimal('1.00'))

        self.client.force_login(manager)
        response = self.client.get(reverse('reports'), {'project': project.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1>Raport projektu</h1>', html=True)
        self.assertContains(response, 'Solo project')
        self.assertContains(response, 'Podsumowanie projektu')
