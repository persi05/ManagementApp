from django.shortcuts import render


ERROR_MESSAGES = {
    400: {
        'title': 'Nieprawidłowe żądanie',
        'message': 'Serwer nie mógł przetworzyć tego żądania.',
    },
    403: {
        'title': 'Brak dostępu',
        'message': 'Nie masz uprawnień do tej strony lub akcji.',
    },
    404: {
        'title': 'Nie znaleziono strony',
        'message': 'Ten adres nie istnieje albo został przeniesiony.',
    },
    500: {
        'title': 'Błąd aplikacji',
        'message': 'Wystąpił problem po stronie aplikacji. Spróbuj ponownie za chwilę.',
    },
}


def error_page(request, status_code=500, exception=None):
    details = ERROR_MESSAGES.get(status_code, ERROR_MESSAGES[500])
    context = {
        'status_code': status_code,
        'error_title': details['title'],
        'error_message': details['message'],
        'exception': exception,
    }
    return render(request, 'error.html', context, status=status_code)


def bad_request(request, exception):
    return error_page(request, 400, exception)


def permission_denied(request, exception):
    return error_page(request, 403, exception)


def page_not_found(request, exception):
    return error_page(request, 404, exception)


def server_error(request):
    return error_page(request, 500)
