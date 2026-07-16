from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from features.accounts.models import UserProfile
from features.employees.models import HourlyRate
from features.projects.models import Project, ProjectAssignment
from features.tasks.models import BoardColumn, Task, TaskWorklog
from features.time_tracking.models import TimeEntry


class ReportsTests(TestCase):
    def test_report_includes_worklogs_regardless_of_task_column(self):
        manager = User.objects.create_user(username='manager-final-report', password='pass')
        employee = User.objects.create_user(username='employee-final-report', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Projekt końcowy')
        ProjectAssignment.objects.create(project=project, user=employee)
        open_column = BoardColumn.objects.create(project=project, name='W trakcie', position=0)
        done_column = BoardColumn.objects.create(project=project, name='Gotowe', position=1, is_done_column=True)
        open_task = Task.objects.create(project=project, column=open_column, title='Zadanie otwarte')
        done_task = Task.objects.create(project=project, column=done_column, title='Zadanie zakończone')
        TaskWorklog.objects.create(task=open_task, user=employee, hours=Decimal('8.00'), visible_to_client=True)
        TaskWorklog.objects.create(task=done_task, user=employee, hours=Decimal('2.00'), visible_to_client=True)

        self.client.force_login(manager)
        response = self.client.get(reverse('reports'), {'visibility': 'management'})

        self.assertContains(response, 'Zadanie zakończone')
        self.assertContains(response, 'Zadanie otwarte')
        self.assertContains(response, '2,00h')
        self.assertEqual(response.context['total_hours'], Decimal('10.00'))

    def test_task_worklog_comment_is_visible_in_report(self):
        manager = User.objects.create_user(username='manager', password='pass')
        employee = User.objects.create_user(username='employee', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Projekt raportowy')
        ProjectAssignment.objects.create(project=project, user=employee)
        column = BoardColumn.objects.create(project=project, name='Zakończone', position=0, is_done_column=True)
        task = Task.objects.create(project=project, column=column, title='Zadanie z komentarzem')
        TaskWorklog.objects.create(
            task=task,
            user=employee,
            date=timezone.localdate(),
            hours=Decimal('1.50'),
            comment='Komentarz do czasu',
            visible_to_client=True,
        )

        self.client.force_login(manager)
        response = self.client.get(reverse('reports'), {'visibility': 'management'})

        self.assertContains(response, '<th>Komentarz</th>', html=True)
        self.assertContains(response, 'Zobacz komentarz')
        self.assertContains(response, 'data-report-comment-modal')
        self.assertContains(response, 'Komentarz do czasu')

    def test_client_report_hides_internal_worklogs_and_people_but_shows_billing(self):
        client = User.objects.create_user(username='client-secure-report', password='pass')
        employee = User.objects.create_user(username='employee-secret-name', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Projekt klienta', client=client, client_hourly_rate=Decimal('250.00'))
        column = BoardColumn.objects.create(project=project, name='Zakończone', position=0, is_done_column=True)
        open_column = BoardColumn.objects.create(project=project, name='W toku', position=1)
        public_task = Task.objects.create(project=project, column=column, title='Widoczna praca')
        open_task = Task.objects.create(project=project, column=open_column, title='Praca w toku')
        private_task = Task.objects.create(project=project, column=column, title='Poufna praca')
        TaskWorklog.objects.create(task=public_task, user=employee, hours=Decimal('2.00'), visible_to_client=True, comment='Komentarz tylko w aplikacji')
        TaskWorklog.objects.create(task=open_task, user=employee, hours=Decimal('3.00'), visible_to_client=True, comment='Komentarz zadania w toku')
        TaskWorklog.objects.create(task=private_task, user=employee, hours=Decimal('5.00'), visible_to_client=False)

        self.client.force_login(client)
        response = self.client.get(reverse('reports'))
        csv_response = self.client.get(reverse('export_csv'))
        pdf_response = self.client.get(reverse('export_pdf'))
        completed_response = self.client.get(reverse('reports'), {'work_scope': 'completed'})
        completed_csv = self.client.get(reverse('export_csv'), {'work_scope': 'completed'})
        completed_pdf = self.client.get(reverse('export_pdf'), {'work_scope': 'completed'})

        self.assertContains(response, 'Widoczna praca')
        self.assertContains(response, 'Praca w toku')
        self.assertContains(response, 'W toku')
        self.assertContains(response, 'Wszystkie')
        self.assertContains(response, 'Zakończone')
        self.assertNotContains(response, 'Poufna praca')
        self.assertNotContains(response, employee.username)
        self.assertContains(response, '500,00 PLN')
        self.assertContains(response, '250,00 PLN/h')
        self.assertEqual(response.context['total_hours'], Decimal('5.00'))
        self.assertEqual(response.context['billing_totals'], [{'currency': 'PLN', 'amount': Decimal('500.00')}])
        csv_body = csv_response.content.decode('utf-8')
        self.assertIn('Stawka', csv_body)
        self.assertIn('500.00', csv_body)
        self.assertNotIn(employee.username, csv_body)
        self.assertNotIn('Komentarz', csv_body)
        self.assertNotIn('Komentarz tylko w aplikacji', csv_body)
        self.assertContains(pdf_response, '500,00 PLN')
        self.assertContains(pdf_response, '250,00 PLN/h')
        self.assertContains(pdf_response, 'Praca w toku')
        self.assertContains(pdf_response, 'W toku')
        self.assertNotContains(pdf_response, 'Komentarz')
        self.assertNotContains(pdf_response, 'Komentarz tylko w aplikacji')

        self.assertEqual(completed_response.context['work_scope'], 'completed')
        self.assertEqual(completed_response.context['total_hours'], Decimal('2.00'))
        self.assertContains(completed_response, 'Widoczna praca')
        self.assertNotContains(completed_response, 'Praca w toku')
        completed_csv_body = completed_csv.content.decode('utf-8')
        self.assertIn('Widoczna praca', completed_csv_body)
        self.assertNotIn('Praca w toku', completed_csv_body)
        self.assertContains(completed_pdf, 'Zakończone prace')
        self.assertContains(completed_pdf, 'Widoczna praca')
        self.assertNotContains(completed_pdf, 'Praca w toku')

    def test_client_report_shows_zero_due_when_no_task_is_completed(self):
        client = User.objects.create_user(username='client-zero-due', password='pass')
        employee = User.objects.create_user(username='employee-zero-due', password='pass')
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project = Project.objects.create(name='Projekt w realizacji', client=client, client_hourly_rate=Decimal('100.00'))
        column = BoardColumn.objects.create(project=project, name='W toku', position=0)
        task = Task.objects.create(project=project, column=column, title='Jeszcze realizowane')
        TaskWorklog.objects.create(task=task, user=employee, hours=Decimal('4.00'), visible_to_client=True)

        self.client.force_login(client)
        response = self.client.get(reverse('reports'))
        pdf_response = self.client.get(reverse('export_pdf'))

        self.assertContains(response, '4,00h')
        self.assertContains(response, 'Jeszcze realizowane')
        self.assertContains(response, '0,00 PLN')
        self.assertNotContains(response, 'Do wyceny')
        self.assertContains(pdf_response, '0,00 PLN')

    def test_employee_report_uses_time_entries_for_payroll_and_project_filter(self):
        employee = User.objects.create_user(username='employee-own-report', password='pass')
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.save()
        project_a = Project.objects.create(name='Projekt A')
        project_b = Project.objects.create(name='Projekt B')
        ProjectAssignment.objects.create(project=project_a, user=employee)
        ProjectAssignment.objects.create(project=project_b, user=employee)
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        HourlyRate.objects.create(user=employee, amount=Decimal('100.00'), valid_from=timezone.localdate() - timedelta(days=10))
        TimeEntry.objects.create(user=employee, project=project_a, start=now - timedelta(hours=4), end=now - timedelta(hours=3), editable_until=now + timedelta(days=1))
        TimeEntry.objects.create(user=employee, project=project_b, start=now - timedelta(hours=3), end=now - timedelta(hours=1), editable_until=now + timedelta(days=1))

        self.client.force_login(employee)
        response = self.client.get(reverse('reports'), {'project': project_a.id})
        csv_response = self.client.get(reverse('export_csv'), {'project': project_a.id})

        self.assertEqual(response.context['employee_work_hours'], Decimal('1'))
        self.assertEqual(response.context['employee_payroll'], Decimal('100.00'))
        self.assertContains(response, 'Projekt A')
        csv_body = csv_response.content.decode('utf-8')
        self.assertIn('Projekt A', csv_body)
        self.assertNotIn('Projekt B', csv_body)

    def test_employee_cannot_filter_report_by_another_employee(self):
        employee = User.objects.create_user(username='employee-own-only', password='pass')
        other = User.objects.create_user(username='employee-other', password='pass')
        for user in (employee, other):
            user.profile.role = UserProfile.Role.EMPLOYEE
            user.profile.save()
        project = Project.objects.create(name='Wspólny projekt')
        ProjectAssignment.objects.create(project=project, user=employee)
        ProjectAssignment.objects.create(project=project, user=other)
        column = BoardColumn.objects.create(project=project, name='Praca', position=0)
        own_task = Task.objects.create(project=project, column=column, title='Własny wpis')
        other_task = Task.objects.create(project=project, column=column, title='Cudzy wpis')
        TaskWorklog.objects.create(task=own_task, user=employee, hours=Decimal('1.00'))
        TaskWorklog.objects.create(task=other_task, user=other, hours=Decimal('7.00'))

        self.client.force_login(employee)
        response = self.client.get(reverse('reports'), {'employee': other.id})

        self.assertContains(response, 'Własny wpis')
        self.assertNotContains(response, 'Cudzy wpis')
        self.assertEqual(response.context['employee_task_hours'], Decimal('1.00'))

    def test_management_payroll_pdf_uses_time_entries_and_historical_rate(self):
        manager = User.objects.create_user(username='manager-payroll-report', password='pass')
        employee = User.objects.create_user(username='employee-payroll-report', password='pass')
        manager.profile.role = UserProfile.Role.MANAGEMENT
        manager.profile.save()
        employee.profile.role = UserProfile.Role.EMPLOYEE
        employee.profile.bank_account = 'PL00 1111 2222 3333'
        employee.profile.save()
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        HourlyRate.objects.create(user=employee, amount=Decimal('80.00'), valid_from=timezone.localdate() - timedelta(days=10))
        TimeEntry.objects.create(user=employee, start=now - timedelta(hours=2), end=now, editable_until=now + timedelta(days=1))

        self.client.force_login(manager)
        response = self.client.get(reverse('export_pdf'), {'report': 'payroll'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PL00 1111 2222 3333')
        self.assertContains(response, '160,00 PLN')
        self.assertEqual(response.context['total_hours'], Decimal('2'))
        self.assertEqual(response.context['total_payroll'], Decimal('160.00'))
