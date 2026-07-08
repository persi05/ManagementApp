from features.tasks.services import create_daily_reminders


class DailyReminderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        create_daily_reminders(request.user)
        return self.get_response(request)
