from datetime import timedelta

from django.db import transaction

from .models import HourlyRate


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
