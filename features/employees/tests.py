from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from features.accounts.models import UserProfile
from features.employees.models import EmployeeCharge, HourlyRate
from features.employees.services import employee_charge_occurrences, employee_charge_total
from features.time_tracking.models import TimeEntry


class EmployeeChargeTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user(username='charge-employee', password='pass')
        self.employee.profile.role = UserProfile.Role.EMPLOYEE
        self.employee.profile.save()
        self.manager = User.objects.create_user(username='charge-manager', password='pass')
        self.manager.profile.role = UserProfile.Role.MANAGEMENT
        self.manager.profile.save()
        self.client_user = User.objects.create_user(username='charge-client', password='pass')
        self.client_user.profile.role = UserProfile.Role.CLIENT
        self.client_user.profile.save()

    def test_manual_charges_use_signed_balance_only_in_selected_month(self):
        EmployeeCharge.objects.create(
            user=self.employee,
            name='Multisport',
            amount=Decimal('80.00'),
            starts_at=timezone.make_aware(datetime(2026, 2, 1, 9, 30)),
        )
        EmployeeCharge.objects.create(
            user=self.employee,
            name='Zwrot VAT',
            amount=Decimal('-50.00'),
            starts_at=timezone.make_aware(datetime(2026, 2, 15, 14, 45)),
        )

        occurrences = employee_charge_occurrences(self.employee, date(2026, 2, 1), date(2026, 3, 1))

        self.assertEqual({item['date'] for item in occurrences}, {date(2026, 2, 1), date(2026, 2, 15)})
        self.assertEqual(employee_charge_total(self.employee, date(2026, 2, 1), date(2026, 3, 1)), Decimal('30.00'))
        self.assertEqual(employee_charge_total(self.employee, date(2026, 3, 1), date(2026, 4, 1)), Decimal('0.00'))

    def test_employee_can_create_own_charge_and_manager_can_create_for_selected_employee(self):
        self.client.force_login(self.employee)
        response = self.client.post(reverse('charges'), {
            'name': 'Paliwo',
            'amount': '120.00',
        })
        current_month = timezone.localdate().strftime('%Y-%m')
        self.assertRedirects(response, f'{reverse("charges")}?month={current_month}')
        own_charge = EmployeeCharge.objects.get(name='Paliwo')
        self.assertEqual(own_charge.user, self.employee)
        self.assertEqual(own_charge.created_by, self.employee)
        self.assertEqual(timezone.localtime(own_charge.starts_at).date(), timezone.localdate())

        self.client.force_login(self.manager)
        response = self.client.post(reverse('charges'), {
            'employee': self.employee.id,
            'name': 'Multisport',
            'amount': '80.00',
            'starts_at': '2026-07-01T08:00',
        })
        self.assertRedirects(response, f'{reverse("charges")}?employee={self.employee.id}&month={current_month}')
        manager_charge = EmployeeCharge.objects.get(name='Multisport')
        self.assertEqual(manager_charge.user, self.employee)
        self.assertEqual(manager_charge.created_by, self.manager)

    def test_employee_cannot_change_closed_charge_but_management_can(self):
        charge = EmployeeCharge.objects.create(
            user=self.employee,
            name='Multisport',
            amount=Decimal('80.00'),
            starts_at=timezone.make_aware(datetime(2026, 2, 10, 8, 0)),
        )

        self.client.force_login(self.employee)
        with patch('features.employees.views.timezone.localdate', return_value=date(2026, 3, 6)):
            response = self.client.post(reverse('delete_charge', args=[charge.id]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(EmployeeCharge.objects.filter(pk=charge.id).exists())

        self.client.force_login(self.manager)
        with patch('features.employees.views.timezone.localdate', return_value=date(2026, 3, 6)):
            response = self.client.post(reverse('delete_charge', args=[charge.id]), {'month': '2026-02'})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(EmployeeCharge.objects.filter(pk=charge.id).exists())

    def test_employee_cannot_add_charge_after_next_month_fifth_but_management_can(self):
        self.client.force_login(self.employee)
        with patch('features.employees.views.timezone.localdate', return_value=date(2026, 3, 6)):
            response = self.client.post(reverse('charges'), {
                'name': 'Paliwo',
                'amount': '120.00',
                'starts_at': '2026-02-10T08:00',
                'month': '2026-02',
            })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(EmployeeCharge.objects.filter(name='Paliwo').exists())

        self.client.force_login(self.manager)
        with patch('features.employees.views.timezone.localdate', return_value=date(2026, 3, 6)):
            response = self.client.post(reverse('charges'), {
                'employee': self.employee.id,
                'name': 'Paliwo',
                'amount': '120.00',
                'starts_at': '2026-02-10T08:00',
                'month': '2026-02',
            })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(EmployeeCharge.objects.filter(name='Paliwo', user=self.employee).exists())

    def test_client_has_no_access_to_charges(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(reverse('charges')).status_code, 403)

    def test_reports_and_pdf_subtract_charge_balance_from_payroll(self):
        HourlyRate.objects.create(user=self.employee, amount=Decimal('100.00'), valid_from=date(2026, 2, 1))
        start = timezone.make_aware(datetime(2026, 2, 10, 8, 0))
        TimeEntry.objects.create(
            user=self.employee,
            start=start,
            end=timezone.make_aware(datetime(2026, 2, 10, 10, 0)),
            editable_until=timezone.make_aware(datetime(2026, 2, 11, 10, 0)),
        )
        EmployeeCharge.objects.create(
            user=self.employee,
            name='Multisport',
            amount=Decimal('80.00'),
            starts_at=timezone.make_aware(datetime(2026, 2, 1, 8, 0)),
        )
        EmployeeCharge.objects.create(
            user=self.employee,
            name='Zwrot VAT',
            amount=Decimal('-50.00'),
            starts_at=timezone.make_aware(datetime(2026, 2, 5, 12, 0)),
        )
        period = {'date_from': '2026-02-01', 'date_to': '2026-02-28'}

        self.client.force_login(self.employee)
        report = self.client.get(reverse('reports'), period)
        pdf = self.client.get(reverse('export_pdf'), period)

        self.assertEqual(report.context['employee_payroll'], Decimal('200.00'))
        self.assertEqual(report.context['employee_charge_total'], Decimal('30.00'))
        self.assertEqual(report.context['employee_payroll_after_charges'], Decimal('170.00'))
        self.assertContains(report, '170,00 PLN')
        self.assertContains(pdf, 'Do wypłaty:')
        self.assertContains(pdf, '170,00 PLN')

        self.client.force_login(self.manager)
        management_report = self.client.get(reverse('reports'), {**period, 'employee': self.employee.id})
        management_pdf = self.client.get(reverse('export_pdf'), {**period, 'report': 'payroll', 'employee': self.employee.id})
        row = management_report.context['employee_summaries'][0]
        self.assertEqual(row['charge_total'], Decimal('30.00'))
        self.assertEqual(row['payroll_after_charges'], Decimal('170.00'))
        self.assertContains(management_pdf, '170,00 PLN')
