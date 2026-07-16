from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from features.accounts.models import UserProfile
from features.employees.models import HourlyRate
from features.time_tracking.models import TimeEntry


def month_bounds(request):
    today = timezone.localdate()
    month = request.GET.get('month')
    if month:
        try:
            start_date = datetime.strptime(month, '%Y-%m').date().replace(day=1)
        except ValueError:
            start_date = today.replace(day=1)
    else:
        start_date = today.replace(day=1)

    if start_date.month == 12:
        next_month = start_date.replace(year=start_date.year + 1, month=1)
    else:
        next_month = start_date.replace(month=start_date.month + 1)

    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(datetime.combine(next_month, time.min))
    return start_date, next_month, start_dt, end_dt


def date_range_bounds(request):
    start_date, default_end, _start_dt, _end_dt = month_bounds(request)
    end_date = default_end - timedelta(days=1)
    raw_start = request.GET.get('date_from')
    raw_end = request.GET.get('date_to')

    if raw_start:
        try:
            start_date = date.fromisoformat(raw_start)
        except ValueError:
            pass

    if raw_end:
        try:
            parsed_end = date.fromisoformat(raw_end)
            if parsed_end >= start_date:
                end_date = parsed_end
        except ValueError:
            pass

    # A lone custom start date can fall after the default month end.  Returning
    # an inverted range made every report look empty even though data existed.
    if end_date < start_date:
        end_date = start_date

    exclusive_end = end_date + timedelta(days=1)
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(datetime.combine(exclusive_end, time.min))
    return start_date, exclusive_end, start_dt, end_dt, end_date


def payroll_amount(user, entries, start_date, end_date):
    total = Decimal('0')
    rates = list(HourlyRate.objects.filter(user=user, valid_from__lt=end_date).order_by('valid_from'))
    for entry in entries:
        entry_date = timezone.localtime(entry.start).date()
        rate = None
        for candidate in rates:
            valid_to = candidate.valid_to or date.max
            if candidate.valid_from <= entry_date <= valid_to:
                rate = candidate
        if rate:
            total += entry.hours * rate.amount
    return total.quantize(Decimal('0.01')) if total else Decimal('0.00')


def employee_month_summaries(start_date, end_date, start_dt, end_dt, employees=None, entries=None):
    if employees is None:
        employees = User.objects.filter(profile__role=UserProfile.Role.EMPLOYEE)
    employees = employees.select_related('profile').order_by('last_name', 'first_name', 'username')
    if entries is None:
        entries = TimeEntry.objects.filter(start__gte=start_dt, start__lt=end_dt)
    rows = []
    for employee in employees:
        employee_entries = list(entries.filter(user=employee).select_related('project', 'task'))
        minutes = sum(entry.duration_minutes for entry in employee_entries)
        payroll = payroll_amount(employee, employee_entries, start_date, end_date)
        rows.append({
            'user': employee,
            'hours': Decimal(minutes) / Decimal(60),
            'payroll': payroll,
            'bank_account': getattr(employee.profile, 'bank_account', ''),
            'current_rate': employee.hourly_rates.order_by('-valid_from').first(),
            'entries_count': len(employee_entries),
        })
    return rows
