from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import EmployeeCharge, HourlyRate


@transaction.atomic
def save_hourly_rate(user, cleaned_data, created_by):
    rate, _ = HourlyRate.objects.update_or_create(
        user=user,
        valid_from=cleaned_data['valid_from'],
        defaults={
            'amount': cleaned_data['amount'],
            'currency': cleaned_data['currency'],
            'valid_to': cleaned_data.get('valid_to'),
            'created_by': created_by,
        },
    )
    normalize_hourly_rate_periods(user, rate)
    return rate


def normalize_hourly_rate_periods(user, rate):
    previous_rates = HourlyRate.objects.filter(user=user, valid_from__lt=rate.valid_from)
    overlapping_previous = previous_rates.filter(valid_to__isnull=True) | previous_rates.filter(valid_to__gte=rate.valid_from)
    overlapping_previous.update(valid_to=rate.valid_from - timedelta(days=1))

    next_rate = HourlyRate.objects.filter(user=user, valid_from__gt=rate.valid_from).order_by('valid_from').first()
    if next_rate and (rate.valid_to is None or rate.valid_to >= next_rate.valid_from):
        rate.valid_to = next_rate.valid_from - timedelta(days=1)
        rate.save(update_fields=['valid_to'])


def employee_charge_occurrences(user, start_date, end_date):
    """Return charge occurrences in the half-open [start_date, end_date) range."""
    start_datetime = timezone.make_aware(datetime.combine(start_date, time.min))
    end_datetime = timezone.make_aware(datetime.combine(end_date, time.min))
    charges = EmployeeCharge.objects.filter(
        user=user,
        starts_at__gte=start_datetime,
        starts_at__lt=end_datetime,
    )
    occurrences = []

    for charge in charges:
        local_start = timezone.localtime(charge.starts_at)
        charge_start_date = local_start.date()
        occurrences.append({
            'charge': charge,
            'date': charge_start_date,
            'occurred_at': local_start,
            'amount': charge.amount,
        })

    return sorted(occurrences, key=lambda item: (item['occurred_at'], item['charge'].created_at), reverse=True)


def employee_charge_total(user, start_date, end_date):
    return sum((item['amount'] for item in employee_charge_occurrences(user, start_date, end_date)), Decimal('0.00'))
