from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from features.accounts.models import UserProfile
from features.projects.models import Project, ProjectAssignment
from features.tasks.models import BoardColumn, Task, TaskWorklog


class ReportsTests(TestCase):
    def test_report_includes_only_worklogs_from_completed_columns(self):
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
        self.assertNotContains(response, 'Zadanie otwarte')
        self.assertContains(response, '2,00h')

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
