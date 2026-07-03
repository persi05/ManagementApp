# Dcode Management — Opis Projektu
 
## 1. Wprowadzenie i cel
 
**Dcode Management** to aplikacja webowa do zarządzania czasem pracy oraz zadaniami zespołu, łącząca funkcje **time trackera** (automatyczne i ręczne rejestrowanie czasu pracy) z systemem zarządzania zadaniami w stylu **Kanban/Trello**. Aplikacja obsługuje trzy role użytkowników o różnym zakresie uprawnień: **Klient**, **Pracownik** i **Management**.
 
Celem projektu jest stworzenie narzędzia, które:
- pozwala pracownikom rejestrować rzeczywisty czas pracy (start/stop, z możliwością samodzielnej korekty tego samego dnia),
- automatycznie wykrywa brak aktywności użytkownika i reaguje odpowiednim powiadomieniem,
- umożliwia zarządzanie projektami i zadaniami w formie tablic Kanban,
- pozwala pracownikom przypisywać przepracowane godziny do konkretnych zadań, z kontrolą tego, co widzi klient,
- daje managementowi wgląd w dane rozliczeniowe pracowników (konto, stawka godzinowa) do celów wypłat,
- generuje raporty i statystyki czasu pracy z możliwością eksportu do CSV/PDF (wraz z danymi do przelewu),
- zapewnia odpowiedni poziom bezpieczeństwa i kontroli dostępu w zależności od roli.
---
 
## 2. Role użytkowników
 
### 👤 Klient
- Ma dostęp wyłącznie do przypisanych mu projektów.
- Może dodawać zadania (karty) w ramach swojego projektu.
- Widzi postęp prac i status zadań.
- Widzi liczbę godzin przepracowanych nad poszczególnymi zadaniami/projektem — **wyłącznie te wpisy godzin, które pracownik oznaczył jako widoczne dla klienta**.
- Nie widzi stawek godzinowych ani żadnych danych rozliczeniowych pracowników — to informacje wyłącznie do wewnętrznego użytku (pracownik/management).
### 👷 Pracownik
- Ma własną zakładkę z licznikiem czasu pracy (start/stop).
- Widzi tylko projekty/zadania, do których został przypisany.
- Ma dostęp do własnych statystyk (godziny dzienne/tygodniowe/miesięczne).
- Może samodzielnie uzupełnić/skorygować zapomniany czas pracy — **wyłącznie w obrębie bieżącego dnia** (patrz sekcja 3.3).
- Zarządza swoimi zadaniami na tablicy Kanban (zmiana statusu, komentarze, checklisty).
- Przy każdym zadaniu może dodać liczbę przepracowanych nad nim godzin (worklog) wraz z opcją **„widoczne dla klienta"**, którą może dowolnie przełączać w dowolnym momencie.
- Widzi własną stawkę godzinową oraz aktualną, orientacyjną kwotę wynagrodzenia za dany okres.
### 🛠️ Management (Admin)
- Pełny dostęp do wszystkich projektów, zadań i użytkowników.
- Tworzy konta, przypisuje role, przypisuje pracowników/klientów do projektów.
- W razie potrzeby może bezpośrednio poprawić dowolny wpis czasu pracy — również starszy niż bieżący dzień — bez oddzielnego procesu akceptacji (pracownik koryguje swoje wpisy sam, na bieżąco).
- Po kliknięciu na pracownika widzi jego **dane rozliczeniowe**: imię i nazwisko, numer konta bankowego, aktualną i historyczne stawki godzinowe.
- Może dodać nową stawkę godzinową z datą obowiązywania (bez utraty poprzednich — patrz sekcja 3.8).
- Generuje raporty zbiorcze i eksportuje dane (CSV/PDF, wraz z danymi do przelewu).
### Macierz uprawnień (skrót)
 
| Funkcja                                              | Klient | Pracownik | Management |
|-------------------------------------------------------|:------:|:---------:|:----------:|
| Logowanie/rejestracja                                 | ✅ | ✅ | ✅ |
| Start/stop licznika czasu pracy                       | ❌ | ✅ | ✅ (opcjonalnie) |
| Ręczna edycja czasu pracy                              | ❌ | ✅ (własne, tylko bieżący dzień) | ✅ (wszystkie, bez ograniczeń) |
| Tworzenie projektów                                    | ❌ | ❌ | ✅ |
| Dodawanie zadań w swoim projekcie                      | ✅ | ✅ | ✅ |
| Dodawanie godzin (worklog) do zadania                  | ❌ | ✅ (własne) | ✅ (wszystkie) |
| Zmiana widoczności wpisu godzin dla klienta            | ❌ | ✅ (własne, w każdej chwili) | ✅ (wszystkie) |
| Podgląd godzin oznaczonych jako widoczne dla klienta   | ✅ | ✅ (własne) | ✅ (wszystkie) |
| Podgląd wszystkich godzin (także niewidocznych dla klienta) | ❌ | ✅ (własne) | ✅ (wszystkie) |
| Podgląd wszystkich projektów                           | ❌ | ❌ | ✅ |
| Podgląd danych rozliczeniowych (konto, stawka)         | ❌ | ✅ (tylko własne) | ✅ (wszystkich) |
| Zmiana/dodanie stawki godzinowej                       | ❌ | ❌ | ✅ |
| Raporty miesięczne (własne)                            | ❌ | ✅ | ✅ |
| Raporty zbiorcze (wszyscy pracownicy)                  | ❌ | ❌ | ✅ |
| Eksport CSV/PDF                                        | ❌ (opcjonalnie własny projekt) | ✅ (własne) | ✅ (wszystkie) |
| Zarządzanie użytkownikami/rolami                       | ❌ | ❌ | ✅ |
 
---
 
## 3. Moduły funkcjonalne
 
### 3.1 Rejestracja, logowanie i bezpieczeństwo kont
 
**Etap 1 (MVP) — login + hasło:**
- Rejestracja użytkownika: login/nazwa użytkownika (lub e-mail) + hasło.
- Logowanie: login + hasło.
- Hashowanie haseł (Django domyślnie: PBKDF2, opcjonalnie argon2) — hasła nigdy nie są przechowywane jawnie.
- Autoryzacja oparta o JWT (`djangorestframework-simplejwt`) lub sesje Django.
- Kontrola dostępu oparta o role (RBAC) — każdy endpoint API weryfikuje uprawnienia (Django/DRF permission classes).
- Reset hasła przez e-mail (link/token resetujący) — jedyny element wymagający e-maila na tym etapie.
- Panel administracyjny do zarządzania kontami (blokowanie, usuwanie, zmiana roli, przypisywanie do projektów) — może bazować na wbudowanym Django Admin, rozszerzonym o potrzebne widoki.
**Etap 2 (rozszerzenie) — weryfikacja e-mail kodem:**
Docelowo dochodzi weryfikacja e-mailem, w jednym z dwóch (lub obu) wariantów:
 
1. *Potwierdzenie adresu e-mail przy rejestracji* — po założeniu konta system generuje jednorazowy kod (np. 6-cyfrowy), wysyła go na podany adres, a użytkownik wpisuje go w formularzu, żeby aktywować konto. Kod ma ograniczoną ważność (np. 15 minut) i można go wysłać ponownie (z limitem prób, żeby nie dało się nim spamować).
2. *Dodatkowa weryfikacja przy logowaniu (odpowiednik 2FA e-mailem)* — po poprawnym loginie i haśle system wysyła jednorazowy kod na e-mail przypisany do konta; dopiero po jego wpisaniu logowanie kończy się sukcesem i wystawiana jest sesja/token. Kod ważny krótko (np. 5–10 minut), z limitem prób wpisania i rate limitingiem na generowanie kolejnych kodów.
Technicznie: wysyłka e-maili przez Django + SMTP (np. SendGrid/Mailgun/Amazon SES), kody przechowywane w bazie lub w cache (np. Redis) z krótkim czasem życia (TTL).
 
Rekomendacja: zacząć od loginu + hasła (etap 1), a weryfikację e-mail kodem dodać w kolejnym etapie — najpierw jako potwierdzenie rejestracji, docelowo opcjonalnie jako dodatkowy krok bezpieczeństwa przy logowaniu.
 
### 3.2 Automatyczne zliczanie czasu pracy
- Przycisk „Rozpocznij pracę” / „Zakończ pracę" widoczny w panelu pracownika.
- Licznik czasu działający „na żywo" od momentu kliknięcia (widoczny np. jako stały widget na ekranie).
- Możliwość zrobienia przerwy (pauza licznika) bez kończenia sesji pracy.
- Historia wszystkich sesji pracy (data, godzina rozpoczęcia, zakończenia, czas trwania).
- Możliwość przypisania sesji pracy do konkretnego projektu/zadania.
### 3.3 Samodzielna edycja i uzupełnianie czasu pracy
- Formularz umożliwiający dodanie lub poprawienie wpisu czasu pracy (data, godzina od–do, projekt, opcjonalny komentarz, np. „zapomniałem kliknąć start").
- Pracownik edytuje/uzupełnia swoje wpisy **samodzielnie, bez akceptacji managementu** — ale wyłącznie w obrębie bieżącego dnia (tego samego dnia, którego dotyczy wpis). Po zmianie daty wpis jest automatycznie blokowany do edycji przez pracownika.
- Jeśli konieczna jest poprawka starszego wpisu (sprzed bieżącego dnia), może jej dokonać wyłącznie management bezpośrednio z panelu administracyjnego.
- Podstawowe informacje o edycji (kto i kiedy ostatnio zmienił wpis) zapisywane są bezpośrednio w rekordzie wpisu — bez potrzeby budowania osobnego systemu logów/audytu na tym etapie projektu.
### 3.4 Wykrywanie nieaktywności użytkownika
- Monitorowanie aktywności użytkownika (ruch myszy, kliknięcia, klawiatura) w trakcie działania licznika.
- Po określonym czasie bez aktywności (domyślnie **30 minut**, wartość konfigurowalna) system wyświetla powiadomienie: dyskretny toast „z boku" jako pierwsze ostrzeżenie, a następnie pełnoekranowy popup „Czy nadal pracujesz?".
- Jeśli użytkownik nie zareaguje w wyznaczonym czasie (**5 minut**), system automatycznie pauzuje licznik i oznacza okres nieaktywności jako „czas nieaktywny" (nie wliczany do godzin pracy).
- Jeśli użytkownik potwierdzi aktywność — licznik działa dalej bez przerwy.
### 3.5 System zadań (Kanban / Trello-like)
- Tablice (boardy) przypisane do konkretnych projektów.
- Kolumny/listy (domyślnie np. *To Do / In Progress / Review / Done*), z możliwością dodawania własnych.
- Karty zadań zawierające: tytuł, opis, osobę przypisaną, termin wykonania, priorytet, etykiety/tagi, checklisty, załączniki, komentarze.
- Przeciąganie kart między kolumnami (drag & drop).
- Historia zmian statusu zadania.
- Powiadomienia o przypisaniu zadania i zmianie jego statusu.
### 3.6 Godziny pracy przypisane do zadań (worklog) i widoczność dla klienta
- Przy każdym zadaniu (karcie) pracownik może dodać wpis: liczba przepracowanych godzin, data, opcjonalny komentarz.
- Każdy taki wpis ma checkbox/toggle **„widoczne dla klienta"** — pracownik ustawia go przy dodawaniu wpisu i **może dowolnie zmieniać w każdej chwili** (także po dodaniu, np. ukryć lub odkryć wpis później).
- Klient na widoku swojego projektu/zadania widzi sumę godzin — wyłącznie z wpisów aktualnie oznaczonych jako widoczne.
- Management i sam pracownik widzą wszystkie wpisy, niezależnie od ustawienia widoczności.
- Wpisy godzin na zadaniu są niezależne od głównego licznika czasu pracy (sekcja 3.2) — służą do dokładniejszego opisania, na co poszedł czas w ramach danego zadania/projektu.
- Na tym etapie moduł pokazuje wyłącznie liczbę godzin, bez żadnych kwot/stawek — stawki i rozliczenia opisane są osobno w sekcji 3.8 i widoczne tylko dla managementu/pracownika.
### 3.7 Zarządzanie projektami
- Management tworzy projekty oraz przypisuje do nich klientów i pracowników.
- Klient widzi wyłącznie swoje projekty i może w ich ramach dodawać zadania.
- Pracownik widzi projekty, do których został przypisany.
- Management ma pełny wgląd we wszystkie projekty.
### 3.8 Dane rozliczeniowe pracownika i stawki godzinowe
- Management, klikając na profil pracownika, widzi jego dane rozliczeniowe: imię i nazwisko, numer konta bankowego, aktualną stawkę godzinową.
- Te dane (numer konta, stawka) są widoczne wyłącznie dla managementu oraz — w zakresie własnych danych — dla samego pracownika. **Klient nigdy ich nie widzi.**
- Stawka godzinowa **nie jest nadpisywana** przy zmianie — każda zmiana tworzy nowy wpis z datą „obowiązuje od", dzięki czemu:
  - zachowana jest pełna historia stawek,
  - podwyżka w trakcie miesiąca jest poprawnie uwzględniana przy rozliczeniu (godziny sprzed zmiany liczone wg starej stawki, po zmianie wg nowej),
  - management wie dokładnie, ile przelać za dany okres, a pracownik może zweryfikować wyliczenie.
- Na podstawie liczby przepracowanych godzin (z licznika i/lub wpisów ręcznych) oraz aktualnej/historycznych stawek system może wyliczyć orientacyjną kwotę wynagrodzenia za wybrany okres — informacyjnie, bez integracji z systemem księgowym/płatniczym (to poza zakresem projektu, chyba że zostanie rozszerzone w przyszłości).
### 3.9 Raporty i statystyki
- Raport miesięczny czasu pracy per pracownik (godziny dziennie/tygodniowo/miesięcznie).
- Raport per projekt (liczba godzin poświęconych przez poszczególnych pracowników).
- Filtrowanie po dacie, pracowniku, projekcie.
- Wykresy (np. słupkowy — godziny dziennie, kołowy — podział czasu na projekty).
- Dashboard z podsumowaniem, np. „Przepracowano w tym miesiącu: X godzin".
### 3.10 Eksport danych
- **Eksport CSV** — surowe dane wpisów czasu pracy (data, godziny, projekt/zadanie, źródło), do dalszej obróbki np. w Excelu.
- **Eksport PDF** — sformatowany dokument, w którym **u góry znajdują się dane do przelewu**: imię i nazwisko pracownika, numer konta bankowego oraz wyliczona kwota wynagrodzenia za dany okres (na podstawie przepracowanych godzin i stawki/stawek obowiązujących w tym czasie); poniżej tabela godzin wraz z podsumowaniem.
- Eksport z danymi do przelewu (numer konta, kwota) dostępny wyłącznie dla managementu oraz danego pracownika (własny eksport) — eksport dostępny dla klienta (jeśli w ogóle udostępniony) nie zawiera tej sekcji, tylko godziny oznaczone jako widoczne dla klienta.
- Możliwość eksportu dla pojedynczego pracownika lub zbiorczo (dla managementu, np. wszyscy pracownicy za dany miesiąc).
---
 
## 4. Model danych (kluczowe encje)
 
- **User** — id, imię, nazwisko, email, hash hasła, rola, status konta, numer konta bankowego *(widoczne tylko dla managementu i właściciela konta)*
- **Project** — id, nazwa, opis, klient_id, data utworzenia, status
- **ProjectAssignment** — project_id, user_id, rola w projekcie (powiązanie pracowników/klientów z projektami)
- **TimeEntry** — id, user_id, project_id, start, koniec, czas trwania, źródło (automatyczny/ręczny), edytowalny_do_daty (domyślnie koniec dnia, którego dotyczy wpis), edytowane_przez, data_edycji
- **Board** — id, project_id, nazwa
- **List/Column** — id, board_id, nazwa, kolejność
- **Task/Card** — id, list_id, tytuł, opis, przypisany user_id, termin, priorytet, etykiety, kolejność
- **TaskWorklog** — id, task_id, user_id, liczba_godzin, data, komentarz, widoczne_dla_klienta (boolean, edytowalne w dowolnym momencie)
- **HourlyRate** — id, user_id, stawka, waluta, obowiązuje_od, obowiązuje_do (uzupełniane automatycznie przy dodaniu kolejnej stawki), utworzone_przez
- **Comment** — id, task_id, user_id, treść, data
- **Attachment** — id, task_id, url, nazwa pliku
- **Notification** — id, user_id, treść, typ, przeczytane, data
---
 
## 5. Wymagania niefunkcjonalne
 
### Bezpieczeństwo
- Wymuszone HTTPS.
- Hashowanie haseł (wbudowane mechanizmy Django) — brak przechowywania hasła jawnym tekstem.
- Walidacja danych wejściowych po stronie backendu (Django/DRF serializers, nie tylko frontend).
- Ochrona przed SQL Injection, XSS i CSRF (Django posiada wbudowane mechanizmy ochronne, wystarczy ich nie wyłączać).
- RBAC — każdy endpoint API weryfikuje rolę i uprawnienia użytkownika (DRF permission classes).
- **Rate limiting**: np. maks. 5 prób logowania na 15 minut z danego IP oraz ogólny limit zapytań API (np. 100 req/min na użytkownika) — realizowane przez DRF throttling lub `django-ratelimit`.
- Krótko żyjące tokeny JWT + mechanizm refresh tokenów (jeśli wybrana zostanie autoryzacja JWT zamiast sesji).
- Restrykcyjna konfiguracja CORS.
- Dane finansowe pracowników (numer konta, stawka godzinowa) dostępne wyłącznie dla roli Management oraz właściciela danych (pracownik widzi tylko swoje) — nigdy dla klienta; warto rozważyć dodatkowe szyfrowanie tych pól w bazie danych.
- Zgodność z RODO (możliwość eksportu/usunięcia danych użytkownika na żądanie).
- Formalny system logów/audytu (kto-co-kiedy zmienił w całym systemie) **nie jest wymagany na tym etapie** — podstawowa rozliczalność jest zapewniona przez historię stawek (`HourlyRate`) oraz metadane edycji na wpisach czasu (`edytowane_przez`, `data_edycji`). Jeśli w przyszłości pojawi się taka potrzeba (np. przy sporach o godziny), można dodać osobny moduł audytu.
### Wydajność i skalowalność
- Paginacja list (zadania, wpisy czasu, projekty).
- Indeksy bazodanowe na często filtrowanych polach (user_id, project_id, data).
- Cache dla raportów (opcjonalnie np. Redis).
### UX
- Pełna responsywność (desktop, tablet, mobile).
- Stale widoczny licznik czasu (sticky widget), gdy aktywna jest sesja pracy.
- Powiadomienia w aplikacji (in-app), opcjonalnie dodatkowo e-mail.
---
 
## 6. Stack technologiczny
 
- **Backend:** Django + Django REST Framework (Python)
- **Frontend:** React (+ TypeScript zalecane)
- **Baza danych:** PostgreSQL
- **Konteneryzacja:** Docker + docker-compose (osobne kontenery: backend, frontend, baza danych, opcjonalnie Redis)
- **Autoryzacja:** sesje Django lub JWT (`djangorestframework-simplejwt`)
- **Rate limiting:** DRF throttling / `django-ratelimit`
- **Zadania w tle / harmonogram** (np. automatyczne blokowanie wpisów czasu po zakończeniu dnia, powiadomienia o nieaktywności, generowanie raportów): Celery + Redis
- **Generowanie PDF:** WeasyPrint lub ReportLab
- **CI/CD:** GitHub Actions
---

## 7. Podsumowanie
 
Dcode Management to system łączący **time tracking** (automatyczny i ręczny, z wykrywaniem nieaktywności i samodzielną korektą wpisów przez pracownika tego samego dnia), **zarządzanie zadaniami w stylu Kanban** z możliwością przypisywania godzin do konkretnych zadań (z w pełni edytowalną widocznością dla klienta), **dane rozliczeniowe i stawki godzinowe pracowników z historią zmian** oraz **raportowanie godzin pracy z eksportem do CSV/PDF zawierającym dane do przelewu** — w architekturze opartej o trzy role użytkowników (Klient, Pracownik, Management), zbudowanej w oparciu o **Django + PostgreSQL** (backend) i **React** (frontend), uruchamianej w kontenerach **Docker**.
