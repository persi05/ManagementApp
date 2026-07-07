from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse


class LoginRateLimitMiddleware:
    """Small session-app rate limit for login POSTs until an API layer is added."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.path == reverse('accounts:login'):
            key = f'login-rate:{self._client_ip(request)}'
            attempts = cache.get(key, 0)
            if attempts >= settings.LOGIN_RATE_LIMIT_ATTEMPTS:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'error': 'Too many login attempts.'}, status=429)
                return HttpResponseForbidden('Za duzo prob logowania. Sprobuj ponownie pozniej.')

            response = self.get_response(request)
            if response.status_code in {301, 302, 303}:
                cache.delete(key)
            else:
                cache.set(key, attempts + 1, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
            return response

        return self.get_response(request)

    @staticmethod
    def _client_ip(request):
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')


class BlockedAccountMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        profile = getattr(user, 'profile', None)
        if getattr(profile, 'is_blocked', False):
            logout(request)
            return HttpResponseForbidden('Konto jest zablokowane.')
        if request.path.startswith('/admin/') and getattr(user, 'is_authenticated', False):
            is_management = getattr(profile, 'role', None) == 'management'
            if not is_management:
                return HttpResponseForbidden('Panel administracyjny jest dostępny tylko dla managementu.')
        return self.get_response(request)
