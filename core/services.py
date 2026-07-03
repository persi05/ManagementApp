from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from .models import BoardColumn, HourlyRate, TimeEntry, UserProfile


DEFAULT_BOARD_COLUMNS = ['Do zrobienia', 'W trakcie', 'Review', 'Zakonczone']


def ensure_default_columns(project):
    for position, name in enumerate(DEFAULT_BOARD_COLUMNS):
        BoardColumn.objects.get_or_create(
            project=project,
            name=name,
            defaults={'position': position},
        )


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


def employee_month_summaries(start_date, end_date, start_dt, end_dt):
    employees = User.objects.filter(profile__role=UserProfile.Role.EMPLOYEE).select_related('profile').order_by('last_name', 'first_name', 'username')
    rows = []
    for employee in employees:
        entries = list(TimeEntry.objects.filter(user=employee, start__gte=start_dt, start__lt=end_dt).select_related('project', 'task'))
        minutes = sum(entry.duration_minutes for entry in entries)
        payroll = payroll_amount(employee, entries, start_date, end_date)
        rows.append({
            'user': employee,
            'hours': Decimal(minutes) / Decimal(60),
            'payroll': payroll,
            'bank_account': getattr(employee.profile, 'bank_account', ''),
            'current_rate': employee.hourly_rates.order_by('-valid_from').first(),
            'entries_count': len(entries),
        })
    return rows
