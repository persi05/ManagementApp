from decimal import Decimal
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from features.accounts.models import UserProfile, is_management
from features.accounts.permissions import management_required, worker_required
from features.employees.forms import EmployeeChargeForm, EmployeeProfileForm, HourlyRateForm, UserRoleForm
from features.employees.models import EmployeeCharge, HourlyRate
from features.employees.services import employee_charge_occurrences, save_hourly_rate
from features.reports.services import date_range_bounds, employee_month_summaries, payroll_amount
from features.time_tracking.models import TimeEntry


POLISH_MONTHS = [
    '',
    'Styczeń',
    'Luty',
    'Marzec',
    'Kwiecień',
    'Maj',
    'Czerwiec',
    'Lipiec',
    'Sierpień',
    'Wrzesień',
    'Październik',
    'Listopad',
    'Grudzień',
]


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=1)


def charge_redirect_url(employee_id=None, month=''):
    params = {}
    if employee_id:
        params['employee'] = employee_id
    if month:
        params['month'] = month
    query = urlencode(params)
    return f'{reverse("charges")}?{query}' if query else reverse('charges')


def charge_change_cutoff(charge):
    charge_date = timezone.localtime(charge.starts_at).date()
    return charge_date_cutoff(charge_date)


def charge_date_cutoff(charge_date):
    first_next_month = add_months(charge_date.replace(day=1), 1)
    return first_next_month + timedelta(days=4)


def can_change_charge(user, charge):
    return is_management(user) or timezone.localdate() <= charge_change_cutoff(charge)


def can_add_charge(user, starts_at):
    return is_management(user) or timezone.localdate() <= charge_date_cutoff(timezone.localtime(starts_at).date())


@login_required
def employees(request):
    forbidden = management_required(request.user)
    if forbidden:
        return forbidden

    start_date, end_date_exclusive, start_dt, end_dt, end_date = date_range_bounds(request)
    summaries = employee_month_summaries(start_date, end_date_exclusive, start_dt, end_dt)
    registered_users = User.objects.select_related('profile').order_by('last_name', 'first_name', 'username')
    return render(request, 'features/employees.html', {
        'employees': summaries,
        'registered_users': registered_users,
        'month': start_date.strftime('%Y-%m'),
        'date_from': start_date.isoformat(),
        'date_to': end_date.isoformat(),
        'period_label': f'{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}',
        'total_hours': sum(row['hours'] for row in summaries),
        'total_payroll': sum(row['payroll'] for row in summaries),
        'total_charges': sum(row['charge_total'] for row in summaries),
        'total_payout': sum(row['payroll_after_charges'] for row in summaries),
    })


@login_required
def employee_detail(request, user_id):
    forbidden = management_required(request.user)
    if forbidden:
        return forbidden

    employee = get_object_or_404(User.objects.select_related('profile'), pk=user_id)
    start_date, end_date_exclusive, start_dt, end_dt, end_date = date_range_bounds(request)
    edit_charge = None
    if request.GET.get('edit_charge'):
        edit_charge = get_object_or_404(EmployeeCharge, pk=request.GET['edit_charge'], user=employee)

    role_form = UserRoleForm(instance=employee.profile)
    profile_form = EmployeeProfileForm(instance=employee.profile)
    rate_form = HourlyRateForm()
    charge_form = EmployeeChargeForm(
        instance=edit_charge,
        initial={} if edit_charge else {'starts_at': timezone.localtime().replace(second=0, microsecond=0)},
    )

    if request.method == 'POST':
        form_name = request.POST.get('form')
        if form_name == 'role':
            role_form = UserRoleForm(request.POST, instance=employee.profile)
            if role_form.is_valid():
                role_form.save()
                messages.success(request, 'Rola użytkownika została zapisana.')
                return redirect('employee_detail', user_id=employee.id)
        elif form_name == 'profile':
            profile_form = EmployeeProfileForm(request.POST, instance=employee.profile)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Dane pracownika zapisane.')
                return redirect('employee_detail', user_id=employee.id)
        elif form_name == 'rate':
            rate_form = HourlyRateForm(request.POST)
            if rate_form.is_valid():
                save_hourly_rate(employee, rate_form.cleaned_data, request.user)
                messages.success(request, 'Stawka została dodana.')
                return redirect('employee_detail', user_id=employee.id)
        elif form_name == 'charge' and employee.profile.role == UserProfile.Role.EMPLOYEE:
            charge = None
            if request.POST.get('charge_id'):
                charge = get_object_or_404(EmployeeCharge, pk=request.POST['charge_id'], user=employee)
            charge_form = EmployeeChargeForm(request.POST, instance=charge)
            if charge_form.is_valid():
                saved_charge = charge_form.save(commit=False)
                saved_charge.user = employee
                if charge and not can_change_charge(request.user, charge):
                    messages.error(request, 'Ten wpis jest już zamknięty do edycji.')
                    return redirect('employee_detail', user_id=employee.id)
                if not charge and not can_add_charge(request.user, saved_charge.starts_at):
                    messages.error(request, 'Nie można już dodać obciążenia za ten miesiąc.')
                    return redirect('employee_detail', user_id=employee.id)
                if not saved_charge.created_by_id:
                    saved_charge.created_by = request.user
                saved_charge.save()
                messages.success(request, 'Obciążenie zostało zapisane.')
                return redirect('employee_detail', user_id=employee.id)

    entries = list(
        TimeEntry.objects.filter(user=employee, start__gte=start_dt, start__lt=end_dt).select_related('project', 'task')
    )
    minutes = sum(entry.duration_minutes for entry in entries)
    rates = HourlyRate.objects.filter(user=employee).order_by('-valid_from')
    charge_items = employee_charge_occurrences(employee, start_date, end_date_exclusive)
    charge_total = sum((item['amount'] for item in charge_items), Decimal('0.00'))
    payroll = payroll_amount(employee, entries, start_date, end_date_exclusive)
    return render(request, 'features/employee_detail.html', {
        'employee': employee,
        'entries': entries,
        'month': start_date.strftime('%Y-%m'),
        'date_from': start_date.isoformat(),
        'date_to': end_date.isoformat(),
        'period_label': f'{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}',
        'hours': Decimal(minutes) / Decimal(60),
        'payroll': payroll,
        'charge_items': charge_items,
        'charge_total': charge_total,
        'payroll_after_charges': payroll - charge_total,
        'employee_charges': EmployeeCharge.objects.filter(user=employee),
        'rates': rates,
        'profile_form': profile_form,
        'role_form': role_form,
        'rate_form': rate_form,
        'charge_form': charge_form,
        'edit_charge': edit_charge,
    })


@login_required
def charges(request):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    can_manage = is_management(request.user)
    employees = User.objects.filter(profile__role=UserProfile.Role.EMPLOYEE).select_related('profile').order_by(
        'last_name', 'first_name', 'username'
    )
    if can_manage:
        selected_employee = request.GET.get('employee') or request.POST.get('employee')
        employee = get_object_or_404(employees, pk=selected_employee) if selected_employee else employees.first()
    else:
        employee = request.user

    start_date, end_date_exclusive, start_dt, end_dt, end_date = date_range_bounds(request)
    selected_month = start_date.replace(day=1)
    previous_month = add_months(selected_month, -1).strftime('%Y-%m')
    next_month = add_months(selected_month, 1).strftime('%Y-%m')
    edit_charge = None
    if employee and request.GET.get('edit'):
        edit_charge = get_object_or_404(EmployeeCharge, pk=request.GET['edit'], user=employee)
        if not can_change_charge(request.user, edit_charge):
            messages.error(request, 'Ten wpis jest już zamknięty do edycji.')
            return redirect(charge_redirect_url(employee.id if can_manage else None, request.GET.get('month') or ''))
    charge_form = EmployeeChargeForm(
        instance=edit_charge,
        initial={} if edit_charge else {'starts_at': timezone.localtime().replace(second=0, microsecond=0)},
    )

    if request.method == 'POST' and employee:
        charge = None
        if request.POST.get('charge_id'):
            charge = get_object_or_404(EmployeeCharge, pk=request.POST['charge_id'], user=employee)
        charge_form = EmployeeChargeForm(request.POST, instance=charge)
        if charge_form.is_valid():
            saved_charge = charge_form.save(commit=False)
            saved_charge.user = employee
            if charge and not can_change_charge(request.user, charge):
                messages.error(request, 'Ten wpis jest już zamknięty do edycji.')
                return redirect(charge_redirect_url(employee.id if can_manage else None, request.POST.get('month') or start_date.strftime('%Y-%m')))
            if not charge and not can_add_charge(request.user, saved_charge.starts_at):
                messages.error(request, 'Nie można już dodać obciążenia za ten miesiąc.')
                return redirect(charge_redirect_url(employee.id if can_manage else None, request.POST.get('month') or start_date.strftime('%Y-%m')))
            if not saved_charge.created_by_id:
                saved_charge.created_by = request.user
            saved_charge.save()
            messages.success(request, 'Obciążenie zostało zapisane.')
            return redirect(charge_redirect_url(employee.id if can_manage else None, request.POST.get('month') or start_date.strftime('%Y-%m')))

    payroll = Decimal('0.00')
    charge_items = []
    charge_total = Decimal('0.00')
    employee_charges = EmployeeCharge.objects.none()
    if employee:
        entries = list(TimeEntry.objects.filter(user=employee, start__gte=start_dt, start__lt=end_dt))
        payroll = payroll_amount(employee, entries, start_date, end_date_exclusive)
        charge_items = employee_charge_occurrences(employee, start_date, end_date_exclusive)
        for item in charge_items:
            item['can_change'] = can_change_charge(request.user, item['charge'])
        charge_total = sum((item['amount'] for item in charge_items), Decimal('0.00'))
        employee_charges = EmployeeCharge.objects.filter(user=employee)

    return render(request, 'features/charges.html', {
        'can_manage': can_manage,
        'employees': employees,
        'employee': employee,
        'selected_employee': str(employee.id) if employee else '',
        'charge_form': charge_form,
        'edit_charge': edit_charge,
        'charge_items': charge_items,
        'employee_charges': employee_charges,
        'charge_total': charge_total,
        'payroll': payroll,
        'payroll_after_charges': payroll - charge_total,
        'month': start_date.strftime('%Y-%m'),
        'month_label': f'{POLISH_MONTHS[selected_month.month]} {selected_month.year}',
        'previous_month': previous_month,
        'next_month': next_month,
        'date_from': start_date.isoformat(),
        'date_to': end_date.isoformat(),
        'period_label': f'{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}',
    })


@login_required
@require_POST
def delete_charge(request, charge_id):
    forbidden = worker_required(request.user)
    if forbidden:
        return forbidden

    charge = get_object_or_404(EmployeeCharge, pk=charge_id)
    if not is_management(request.user) and charge.user_id != request.user.id:
        return HttpResponseForbidden('Brak uprawnień.')
    if not can_change_charge(request.user, charge):
        messages.error(request, 'Ten wpis jest już zamknięty do usunięcia.')
        return redirect(charge_redirect_url(charge.user_id if is_management(request.user) else None, request.POST.get('month') or ''))
    employee_id = charge.user_id
    charge.delete()
    messages.success(request, 'Obciążenie zostało usunięte.')
    return redirect(charge_redirect_url(employee_id if is_management(request.user) else None, request.POST.get('month') or ''))
