# App Management

App Management to aplikacja webowa do zarządzania pracą zespołu, projektami, zadaniami, czasem pracy, dokumentami oraz rozliczeniami pracowników. Projekt jest zbudowany w Django, korzysta z PostgreSQL i Redis, a lokalnie uruchamia się przez Docker Compose.

## Najważniejsze funkcjonalności

### Role użytkowników

Aplikacja rozróżnia trzy główne role:

- `management` — pełny dostęp do projektów, pracowników, raportów, stawek i rozliczeń.
- `employee` — dostęp do własnej pracy, przypisanych projektów, zadań, czasu pracy, obciążeń i raportów.
- `client` — dostęp tylko do obszarów klienta, bez danych rozliczeniowych pracowników.

### Dashboard

Panel główny pokazuje najważniejsze informacje operacyjne, skróty do modułów i podsumowania zależne od roli zalogowanego użytkownika.

### Projekty

Moduł projektów pozwala:

- tworzyć i edytować projekty,
- przypisywać klientów oraz pracowników,
- ustawiać stawki projektowe dla klienta,
- kontrolować dostęp do projektów według roli użytkownika.

### Zadania / Kanban

Moduł zadań działa jako tablica Kanban:

- kolumny i karty zadań,
- przypisywanie osób do zadań,
- etykiety, priorytety, terminy i opisy,
- komentarze/notatki edycji,
- uprawnienia do widoczności i tworzenia kolumn,
- powiadomienia o istotnych zmianach.

### Czas pracy

Aplikacja obsługuje rejestrowanie czasu pracy:

- licznik start/stop,
- pauzy i wykrywanie nieaktywności,
- ręczne wpisy czasu,
- historia wpisów,
- ograniczenia edycji dla pracowników,
- możliwość zarządzania wpisami przez management.

### Worklogi zadań

Do zadań można dopisywać przepracowane godziny:

- wpisy godzin na konkretnych zadaniach,
- widoczność wpisu dla klienta,
- filtrowanie i podsumowania w raportach.

### Pracownicy i stawki

Management może zarządzać danymi pracowników:

- dane profilu i rozliczeń,
- numer konta bankowego,
- aktualne i historyczne stawki godzinowe,
- szczegóły wynagrodzenia i obciążeń.

### Obciążenia pracowników

Moduł obciążeń pozwala rozliczać dodatkowe kwoty przy wypłacie:

- pracownik może dodawać własne obciążenia,
- management może dodawać obciążenia dla pracownika,
- kwota dodatnia pomniejsza wypłatę,
- kwota ujemna zwiększa wypłatę,
- obciążenia są ręcznie wpisywane dla konkretnego miesiąca,
- pracownik może dodawać, edytować i usuwać obciążenia tylko do 5. dnia następnego miesiąca,
- management może edytować obciążenia zawsze,
- obciążenia są uwzględniane w raportach i podsumowaniu wypłaty.

### Raporty

Raporty obejmują:

- filtrowanie po okresie, pracowniku i projekcie,
- podsumowanie godzin,
- wynagrodzenie na podstawie stawek,
- obciążenia pracownika,
- kwotę do wypłaty po obciążeniach,
- eksport CSV,
- eksport PDF z danymi do przelewu.

### Dokumenty i pliki

Moduł dokumentów umożliwia:

- dodawanie plików,
- przypisywanie plików do projektów,
- kontrolę widoczności,
- limity uploadu i dozwolonych rozszerzeń konfigurowane przez zmienne środowiskowe.

### Kalendarz / planner

Aplikacja zawiera moduł planowania i kalendarza, wykorzystywany m.in. do widoku terminów oraz planowania pracy.

### Powiadomienia

System posiada powiadomienia wewnętrzne oraz mechanizm okresowego czyszczenia starych powiadomień.

## Stack technologiczny

- Python
- Django 6
- PostgreSQL 17
- Redis 7
- WhiteNoise do plików statycznych
- Docker / Docker Compose
- HTML, CSS i JavaScript bez osobnego frontendu SPA

## Wymagania lokalne

Do uruchomienia projektu lokalnie potrzebne są:

- Docker
- Docker Compose
- opcjonalnie `make`, jeśli chcesz używać skrótów z `Makefile`

## Uruchomienie lokalne

1. Skopiuj plik ze zmiennymi środowiskowymi:

```bash
cp .env.example .env
```

Na Windowsie możesz też po prostu skopiować `.env.example` jako `.env`.

2. Uruchom kontenery:

```bash
docker compose up -d --build
```

Albo przez `make`:

```bash
make rebuild
```

3. Aplikacja będzie dostępna pod adresem:

```text
http://127.0.0.1:8000
```

Entry point kontenera automatycznie wykonuje:

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

## Tworzenie konta administratora

Po uruchomieniu kontenerów utwórz superusera:

```bash
docker compose exec web python manage.py createsuperuser
```

Panel administracyjny Django:

```text
http://127.0.0.1:8000/admin/
```

## Przydatne komendy

### Start aplikacji

```bash
docker compose up -d
```

lub:

```bash
make up
```

### Zatrzymanie aplikacji

```bash
docker compose down
```

lub:

```bash
make down
```

### Logi

```bash
docker compose logs -f
```

lub:

```bash
make logs
```

### Wejście do kontenera aplikacji

```bash
docker compose exec web sh
```

lub:

```bash
make shell
```

### Migracje

Utworzenie nowych migracji:

```bash
docker compose exec web python manage.py makemigrations
```

lub:

```bash
make migrations
```

Wykonanie migracji:

```bash
docker compose exec web python manage.py migrate
```

lub:

```bash
make migrate
```

### Testy

```bash
docker compose exec web python manage.py test
```

lub:

```bash
make test
```

### Sprawdzenie konfiguracji Django

```bash
docker compose exec web python manage.py check
```

### Reset lokalnej bazy danych

Uwaga: ta komenda usuwa wolumen PostgreSQL i dane lokalnej bazy.

```bash
docker compose down -v --remove-orphans
```

lub:

```bash
make reset
```

Po resecie uruchom ponownie kontenery i utwórz konto administratora od nowa.

## Zmienne środowiskowe

Projekt wymaga pliku `.env`. Przykład znajduje się w `.env.example`.

Najważniejsze zmienne:

| Zmienna | Opis |
| --- | --- |
| `DJANGO_SECRET_KEY` | Sekretny klucz Django. W produkcji musi być unikalny i tajny. |
| `DJANGO_DEBUG` | `true` lokalnie, `false` w produkcji. |
| `DJANGO_ALLOWED_HOSTS` | Lista hostów oddzielona przecinkami. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Zaufane originy CSRF, np. lokalny adres aplikacji. |
| `DATABASE_URL` | URL połączenia z PostgreSQL. |
| `REDIS_URL` | URL połączenia z Redis. |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | Liczba prób logowania w oknie czasowym. |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | Długość okna limitu logowania w sekundach. |
| `DOCUMENTS_MAX_UPLOAD_SIZE_BYTES` | Maksymalny rozmiar uploadowanego pliku. |
| `DOCUMENTS_MAX_FILES_PER_USER` | Maksymalna liczba plików użytkownika. |
| `DOCUMENTS_ALLOWED_UPLOAD_EXTENSIONS` | Dozwolone rozszerzenia plików. |
| `NOTIFICATIONS_PER_PAGE` | Liczba powiadomień na stronę. |
| `NOTIFICATIONS_READ_RETENTION_DAYS` | Retencja przeczytanych powiadomień. |
| `NOTIFICATIONS_UNREAD_RETENTION_DAYS` | Retencja nieprzeczytanych powiadomień. |

## Struktura projektu

```text
config/                 ustawienia Django, URL-e główne, ASGI/WSGI
features/accounts/      konta, role, logowanie, profile użytkowników
features/dashboard/     dashboard i landing
features/projects/      projekty i przypisania
features/tasks/         Kanban, zadania, powiadomienia
features/time_tracking/ czas pracy i timer
features/employees/     pracownicy, stawki, obciążenia
features/reports/       raporty i eksporty
features/documents/     dokumenty i upload plików
features/planner/       kalendarz i planowanie
static/                 CSS i JavaScript
templates/              szablony HTML
docker/                 entrypoint kontenera
docs/                   dokumentacja projektowa i materiały pomocnicze
```

## Środowisko produkcyjne

Do produkcji należy przygotować osobny `.env` na podstawie `.env.production.example`.

Minimalnie trzeba ustawić:

- `DJANGO_DEBUG=false`,
- mocny `DJANGO_SECRET_KEY`,
- prawidłowe `DJANGO_ALLOWED_HOSTS`,
- prawidłowe `DJANGO_CSRF_TRUSTED_ORIGINS`,
- produkcyjny `DATABASE_URL`,
- produkcyjny `REDIS_URL`,
- ustawienia HTTPS/proxy zgodne z infrastrukturą.

Przy `DJANGO_DEBUG=false` Django wymusza bezpieczniejsze ustawienia cookies, HSTS i statyczne pliki przez WhiteNoise.

## Dokumentacja dodatkowa

W katalogu `docs/` znajduje się szerszy opis wymagań i założeń projektowych:

```text
docs/requirements.md
```

Ten plik README opisuje praktyczne uruchomienie i aktualne moduły aplikacji.
