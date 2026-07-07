from .models import BoardColumn


DEFAULT_BOARD_COLUMNS = ['Do zrobienia', 'W trakcie', 'Review', 'Zakonczone']


def ensure_default_columns(project):
    for position, name in enumerate(DEFAULT_BOARD_COLUMNS):
        BoardColumn.objects.get_or_create(
            project=project,
            name=name,
            defaults={'position': position},
        )
