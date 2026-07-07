from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from features.accounts.models import UserProfile
from features.accounts.permissions import management_required
from features.employees.forms import EmployeeProfileForm, HourlyRateForm, UserRoleForm
from features.employees.models import HourlyRate
from features.reports.services import employee_month_summaries, month_bounds, payroll_amount
from features.time_tracking.models import TimeEntry


@login_required
def employees(request):
    forbidden = management_required(request.user)
    if forbidden:
        return forbidden

    start_date, next_month, start_dt, end_dt = month_bounds(request)
    summaries = employee_month_summaries(start_date, next_month, start_dt, end_dt)
    registered_users = User.objects.select_related('profile').order_by('last_name', 'first_name', 'username')
    return render(request, 'features/employees.html', {
        'employees': summaries,
        'registered_users': registered_users,
        'month': start_date.strftime('%Y-%m'),
        'total_hours': sum(row['hours'] for row in summaries),
        'total_payroll': sum(row['payroll'] for row in summaries),
    })


@login_required
def employee_detail(request, user_id):
    forbidden = management_required(request.user)
    if forbidden:
        return forbidden

    employee = get_object_or_404(User.objects.select_related('profile'), pk=user_id)
    start_date, next_month, start_dt, end_dt = month_bounds(request)

    if request.method == 'POST':
        if request.POST.get('form') == 'role':
            role_form = UserRoleForm(request.POST, instance=employee.profile)
            profile_form = EmployeeProfileForm(instance=employee.profile)
            rate_form = HourlyRateForm()
            if role_form.is_valid():
                role_form.save()
                employee.is_staff = employee.profile.role == UserProfile.Role.MANAGEMENT
                if employee.profile.role != UserProfile.Role.MANAGEMENT:
                    employee.is_superuser = False
                employee.save(update_fields=['is_staff', 'is_superuser'])
                messages.success(request, 'Rola użytkownika została zapisana.')
                return redirect('employee_detail', user_id=employee.id)
        elif request.POST.get('form') == 'profile':
            role_form = UserRoleForm(instance=employee.profile)
            profile_form = EmployeeProfileForm(request.POST, instance=employee.profile)
            rate_form = HourlyRateForm()
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Dane pracownika zapisane.')
                return redirect('employee_detail', user_id=employee.id)
        elif request.POST.get('form') == 'rate':
            role_form = UserRoleForm(instance=employee.profile)
            profile_form = EmployeeProfileForm(instance=employee.profile)
            rate_form = HourlyRateForm(request.POST)
            if rate_form.is_valid():
                rate = rate_form.save(commit=False)
                rate.user = employee
                rate.created_by = request.user
                rate.save()
                messages.success(request, 'Stawka została dodana.')
                return redirect('employee_detail', user_id=employee.id)
        else:
            role_form = UserRoleForm(instance=employee.profile)
            profile_form = EmployeeProfileForm(instance=employee.profile)
            rate_form = HourlyRateForm()
    else:
        role_form = UserRoleForm(instance=employee.profile)
        profile_form = EmployeeProfileForm(instance=employee.profile)
        rate_form = HourlyRateForm()

    entries = list(TimeEntry.objects.filter(user=employee, start__gte=start_dt, start__lt=end_dt).select_related('project', 'task'))
    minutes = sum(entry.duration_minutes for entry in entries)
    rates = HourlyRate.objects.filter(user=employee).order_by('-valid_from')
    return render(request, 'features/employee_detail.html', {
        'employee': employee,
        'entries': entries,
        'month': start_date.strftime('%Y-%m'),
        'hours': Decimal(minutes) / Decimal(60),
        'payroll': payroll_amount(employee, entries, start_date, next_month),
        'rates': rates,
        'profile_form': profile_form,
        'role_form': role_form,
        'rate_form': rate_form,
    })
