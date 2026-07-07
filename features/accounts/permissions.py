from django.http import HttpResponseForbidden

from .models import UserProfile, is_management, user_role


def optional_pk(value):
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def management_required(user):
    if not is_management(user):
        return HttpResponseForbidden('Brak uprawnień.')
    return None


def worker_required(user):
    if user_role(user) == UserProfile.Role.CLIENT:
        return HttpResponseForbidden('Klient nie ma dostępu do rejestracji czasu pracy.')
    return None
