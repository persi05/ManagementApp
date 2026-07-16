from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from features.accounts.models import UserProfile, ensure_profile
from features.employees.models import HourlyRate
from features.projects.models import Project, ProjectAssignment
from features.tasks.models import BoardColumn, ChecklistItem, Task, TaskWorklog
from features.time_tracking.models import TimeEntry


class Command(BaseCommand):
    help = 'Tworzy dane demonstracyjne dla Dcode Management.'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('seed_demo can only be run when DJANGO_DEBUG=true.')

        manager = self.user('manager', 'Manager', 'Dcode', UserProfile.Role.MANAGEMENT, True)
        employee = self.user('pracownik', 'Anna', 'Nowak', UserProfile.Role.EMPLOYEE)
        employee2 = self.user('dev', 'Piotr', 'Kowalski', UserProfile.Role.EMPLOYEE)
        client = self.user('klient', 'Klara', 'Zielińska', UserProfile.Role.CLIENT)

        ensure_profile(employee).bank_account = '12 1020 1026 0000 0422 7020 1111'
        employee.profile.save()
        ensure_profile(employee2).bank_account = '44 2490 0005 0000 4530 9988 2200'
        employee2.profile.save()

        HourlyRate.objects.get_or_create(user=employee, valid_from=timezone.localdate().replace(day=1), defaults={'amount': Decimal('120.00'), 'created_by': manager})
        HourlyRate.objects.get_or_create(user=employee2, valid_from=timezone.localdate().replace(day=1), defaults={'amount': Decimal('150.00'), 'created_by': manager})

        atlas, _ = Project.objects.get_or_create(name='Atlas CRM', defaults={'client': client, 'description': 'Panel klienta i raportowanie czasu.'})
        orbit, _ = Project.objects.get_or_create(name='Orbit Billing', defaults={'client': client, 'description': 'Automatyzacja rozliczeń i eksportów.'})
        for project in (atlas, orbit):
            for user, role in ((client, ProjectAssignment.ProjectRole.CLIENT), (employee, ProjectAssignment.ProjectRole.EMPLOYEE), (employee2, ProjectAssignment.ProjectRole.LEAD)):
                ProjectAssignment.objects.get_or_create(project=project, user=user, defaults={'project_role': role})
            column_names = ['Do zrobienia', 'W trakcie', 'Review', 'Zakończone']
            for idx, name in enumerate(column_names):
                BoardColumn.objects.get_or_create(
                    project=project,
                    name=name,
                    defaults={'position': idx, 'is_done_column': idx == len(column_names) - 1},
                )

        todo = atlas.columns.get(name='Do zrobienia')
        doing = atlas.columns.get(name='W trakcie')
        review = atlas.columns.get(name='Review')
        done = atlas.columns.get(name='Zakończone')
        tasks = [
            (atlas, todo, 'Dodać widok rozliczeń klienta', employee, 'high'),
            (atlas, doing, 'Implementacja timera z pauzą', employee, 'high'),
            (atlas, review, 'Test eksportu CSV', employee2, 'medium'),
            (atlas, done, 'Makieta tablicy Kanban', employee2, 'low'),
            (orbit, orbit.columns.get(name='W trakcie'), 'PDF z danymi do przelewu', employee, 'medium'),
        ]
        created_tasks = []
        for project, column, title, assignee, priority in tasks:
            task, _ = Task.objects.get_or_create(
                project=project,
                title=title,
                defaults={'column': column, 'assignee': assignee, 'priority': priority, 'created_by': manager, 'description': 'Zadanie demonstracyjne z wymaganiami MVP.'},
            )
            created_tasks.append(task)
            ChecklistItem.objects.get_or_create(task=task, text='Analiza wymagań', defaults={'is_done': True})
            ChecklistItem.objects.get_or_create(task=task, text='Implementacja', defaults={'is_done': column.name in ['Review', 'Zakończone']})
            TaskWorklog.objects.get_or_create(task=task, user=assignee, date=timezone.localdate(), defaults={'hours': Decimal('2.50'), 'visible_to_client': column.name != 'Do zrobienia'})

        today = timezone.localdate()
        for days_ago in range(0, 8):
            day = today - timedelta(days=days_ago)
            start = timezone.make_aware(datetime.combine(day, time(9, 0)))
            end = timezone.make_aware(datetime.combine(day, time(15 + (days_ago % 3), 30)))
            TimeEntry.objects.get_or_create(
                user=employee,
                start=start,
                defaults={'project': atlas, 'task': created_tasks[0], 'end': end, 'source': TimeEntry.Source.AUTO, 'editable_until': timezone.make_aware(datetime.combine(day, time.max))},
            )

        self.stdout.write(self.style.SUCCESS('Dane demo gotowe. Loginy: manager / pracownik / dev / klient, hasło: demo12345'))

    def user(self, username, first_name, last_name, role, superuser=False):
        user, created = User.objects.get_or_create(username=username, defaults={'first_name': first_name, 'last_name': last_name, 'email': f'{username}@example.com'})
        if created:
            user.set_password('demo12345')
        user.first_name = first_name
        user.last_name = last_name
        user.is_staff = superuser
        user.is_superuser = superuser
        user.save()
        profile = ensure_profile(user)
        profile.role = role
        profile.save()
        return user
