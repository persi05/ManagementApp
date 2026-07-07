from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'features.accounts'

    def ready(self):
        import features.accounts.signals  # noqa: F401
