# Software Requirements Specification

##  App Management

| Pole | Wartość |
| --- | --- |
| Nazwa systemu |  App Management |
| Typ dokumentu | Software Requirements Specification |
| Wersja dokumentu | 1.0 |
| Data | 17.07.2026 |
| Język dokumentu | Polski |
| Status | Aktualny opis wymagań i działania aplikacji |

## Historia zmian

| Wersja | Data | Autor | Opis |
| --- | --- | --- | --- |
| 1.0 | 17.07.2026 | Zespół projektu | Przepisanie dokumentacji do formatu SRS, aktualizacja zakresu funkcjonalnego i przeniesienie dokumentu do katalogu głównego repozytorium. |

## Spis treści

1. [Wprowadzenie](#1-wprowadzenie)
2. [Opis ogólny systemu](#2-opis-ogólny-systemu)
3. [Role i użytkownicy](#3-role-i-użytkownicy)
4. [Wymagania funkcjonalne](#4-wymagania-funkcjonalne)
5. [Wymagania niefunkcjonalne](#5-wymagania-niefunkcjonalne)
6. [Reguły biznesowe](#6-reguły-biznesowe)
7. [Model danych](#7-model-danych)
8. [Interfejsy zewnętrzne](#8-interfejsy-zewnętrzne)
9. [Przypadki użycia](#9-przypadki-użycia)
10. [Kryteria akceptacji](#10-kryteria-akceptacji)
11. [Środowisko i uruchomienie](#11-środowisko-i-uruchomienie)
12. [Zakres poza projektem](#12-zakres-poza-projektem)
13. [Słownik pojęć](#13-słownik-pojęć)

---

# 1. Wprowadzenie

## 1.1 Cel dokumentu

Celem dokumentu jest opisanie wymagań systemowych, funkcjonalnych i niefunkcjonalnych aplikacji  App Management. Dokument ma służyć jako wspólna podstawa dla programistów, testerów, właściciela produktu oraz osób wdrażających system.

Dokument opisuje aktualny docelowy zakres aplikacji, w tym:

- zarządzanie projektami,
- zarządzanie zadaniami w widoku Kanban,
- rejestrowanie czasu pracy,
- worklogi zadań,
- raporty i eksporty,
- pracowników, stawki godzinowe i obciążenia,
- dokumenty i pliki,
- kalendarz, urlopy i powiadomienia,
- role oraz kontrolę dostępu.

## 1.2 Zakres systemu

 App Management jest webową aplikacją do organizacji pracy małego lub średniego zespołu usługowego. System łączy funkcje zarządzania projektami, zadaniami, czasem pracy i rozliczeniami pracowników.

Głównym celem systemu jest umożliwienie:

- pracownikom rejestrowania pracy i rozliczania własnych godzin,
- managementowi zarządzania projektami, pracownikami i rozliczeniami,
- klientom śledzenia przypisanych projektów i widocznych dla nich postępów,
- generowania raportów dla pracowników, klientów i managementu.

## 1.3 Grupa docelowa dokumentu

Dokument jest przeznaczony dla:

- właściciela produktu,
- programistów backendu i frontendu,
- testerów,
- administratorów wdrożenia,
- osób odpowiedzialnych za utrzymanie systemu,
- osób analizujących zakres biznesowy aplikacji.

## 1.4 Konwencje dokumentu

Wymagania funkcjonalne są oznaczane prefiksem `FR`.

Wymagania niefunkcjonalne są oznaczane prefiksem `NFR`.

Reguły biznesowe są oznaczane prefiksem `BR`.

Przypadki użycia są oznaczane prefiksem `UC`.

---

# 2. Opis ogólny systemu

## 2.1 Perspektywa produktu

 App Management jest samodzielną aplikacją webową opartą o Django. System działa jako klasyczna aplikacja serwerowa renderująca szablony HTML, z dodatkowymi skryptami JavaScript dla interaktywnych elementów interfejsu.

System korzysta z:

- PostgreSQL jako głównej bazy danych,
- Redis jako cache i komponentu pomocniczego,
- sesji Django do uwierzytelniania,
- WhiteNoise do obsługi plików statycznych,
- Docker Compose do lokalnego uruchomienia.

## 2.2 Główne moduły

System składa się z następujących modułów:

| Moduł | Opis |
| --- | --- |
| Konta | Rejestracja, logowanie, profile, role i blokowanie kont. |
| Dashboard | Główny panel użytkownika z podsumowaniami zależnymi od roli. |
| Projekty | Projekty, klienci, przypisania pracowników, stawki klienta i stawki etykiet. |
| Zadania | Tablice Kanban, kolumny, zadania, przypisania, etykiety, komentarze i załączniki. |
| Czas pracy | Timer start/pauza/wznowienie/stop oraz ręczne wpisy czasu. |
| Worklogi | Godziny przypisywane bezpośrednio do zadań. |
| Pracownicy | Lista pracowników, szczegóły, dane rozliczeniowe i stawki godzinowe. |
| Obciążenia | Kwoty pomniejszające lub zwiększające wypłatę pracownika. |
| Raporty | Raporty projektowe, pracownicze, payroll, CSV i PDF. |
| Dokumenty | Foldery, dokumenty tekstowe, pliki, zdjęcia, dostęp i widoczność. |
| Kalendarz | Widok pracy, terminów zadań, wniosków urlopowych i obecności. |
| Powiadomienia | Powiadomienia o zadaniach, notatkach, urlopach i przypomnieniach. |

## 2.3 Klasy użytkowników

System obsługuje trzy role biznesowe:

- klient,
- pracownik,
- management.

Dodatkowo Django posiada techniczną rolę superusera. Superuser jest traktowany jak management w aplikacji oraz ma dostęp do panelu administracyjnego Django.

## 2.4 Ograniczenia technologiczne

System:

- nie jest aplikacją SPA,
- nie wymaga osobnego frontendu React,
- działa jako aplikacja Django z szablonami,
- powinien być uruchamiany lokalnie przez Docker Compose,
- powinien mieć wszystkie zmienne środowiskowe zdefiniowane w `.env`.

---

# 3. Role i użytkownicy

## 3.1 Klient

Klient jest użytkownikiem zewnętrznym. Ma dostęp wyłącznie do przypisanych projektów i danych przeznaczonych dla klienta.

Klient może:

- logować się do aplikacji,
- widzieć przypisane projekty,
- widzieć zadania w kolumnach, do których ma dostęp,
- tworzyć lub edytować zadania zgodnie z uprawnieniami kolumn,
- widzieć worklogi oznaczone jako widoczne dla klienta,
- widzieć raport projektowy w zakresie danych klienckich,
- widzieć kwoty rozliczeniowe projektu, jeśli wynikają ze stawek klienta.

Klient nie może:

- widzieć stawek godzinowych pracowników,
- widzieć numerów kont bankowych pracowników,
- widzieć wewnętrznych wpisów czasu pracy,
- korzystać z modułu obciążeń,
- zarządzać pracownikami,
- widzieć raportów payroll.

## 3.2 Pracownik

Pracownik jest użytkownikiem wewnętrznym wykonującym pracę w projektach.

Pracownik może:

- korzystać z timera czasu pracy,
- dodawać ręczne wpisy czasu pracy,
- edytować własne wpisy czasu w dozwolonym terminie,
- widzieć przypisane projekty i zadania,
- dodawać worklogi do zadań,
- ustawiać widoczność worklogów dla klienta,
- widzieć własne raporty,
- widzieć własne wynagrodzenie wynikające ze stawek,
- dodawać własne obciążenia,
- edytować i usuwać własne obciążenia w dozwolonym terminie,
- składać wnioski urlopowe,
- widzieć własny kalendarz.

Pracownik nie może:

- zarządzać innymi pracownikami,
- zmieniać stawek godzinowych,
- widzieć danych rozliczeniowych innych pracowników,
- widzieć raportów zbiorczych payroll,
- edytować obciążeń po terminie.

## 3.3 Management

Management jest rolą administracyjną w aplikacji biznesowej.

Management może:

- widzieć wszystkie projekty,
- tworzyć i edytować projekty,
- przypisywać klientów i pracowników do projektów,
- zarządzać tablicami Kanban,
- zarządzać uprawnieniami kolumn,
- zarządzać zadaniami,
- widzieć raporty projektowe i pracownicze,
- widzieć dane rozliczeniowe pracowników,
- dodawać i aktualizować stawki godzinowe pracowników,
- dodawać, edytować i usuwać obciążenia pracowników,
- generować raporty payroll,
- akceptować lub odrzucać wnioski urlopowe,
- widzieć obecność pracowników w kalendarzu.

## 3.4 Macierz uprawnień

| Funkcja | Klient | Pracownik | Management |
| --- | :---: | :---: | :---: |
| Logowanie | Tak | Tak | Tak |
| Rejestracja | Tak | Tak | Tak |
| Widok dashboardu | Tak | Tak | Tak |
| Widok przypisanych projektów | Tak | Tak | Tak |
| Widok wszystkich projektów | Nie | Nie | Tak |
| Tworzenie projektów | Nie | Nie | Tak |
| Przypisywanie użytkowników do projektów | Nie | Nie | Tak |
| Widok Kanban | Tak, ograniczony | Tak | Tak |
| Zarządzanie kolumnami | Nie | Nie | Tak |
| Tworzenie zadań | Według uprawnień kolumn | Według uprawnień kolumn | Tak |
| Edycja zadań | Według uprawnień kolumn | Według uprawnień kolumn | Tak |
| Usuwanie zadań | Według uprawnień kolumn | Według uprawnień kolumn | Tak |
| Timer czasu pracy | Nie | Tak | Tak |
| Ręczne wpisy czasu pracy | Nie | Tak, własne | Tak |
| Worklogi zadań | Nie | Tak, własne | Tak |
| Widoczność worklogów dla klienta | Widzi tylko widoczne | Ustawia własne | Zarządza |
| Raport klienta/projektu | Tak, ograniczony | Tak, własny zakres | Tak |
| Raport payroll | Nie | Własny | Tak, zbiorczy |
| Dane bankowe pracownika | Nie | Własne | Tak |
| Stawki godzinowe pracownika | Nie | Własne | Tak |
| Obciążenia | Nie | Własne | Tak |
| Dokumenty | Według dostępu | Według dostępu | Tak |
| Urlopy | Nie | Składa wniosek | Zatwierdza/odrzuca |
| Panel admin Django | Nie | Nie | Tylko superuser |

---

# 4. Wymagania funkcjonalne

## 4.1 Konta i uwierzytelnianie

### FR-ACC-001 — Rejestracja użytkownika

System musi umożliwiać rejestrację użytkownika przez formularz rejestracyjny.

### FR-ACC-002 — Profil użytkownika

System musi tworzyć profil użytkownika powiązany z kontem Django.

Profil musi przechowywać:

- rolę użytkownika,
- numer konta bankowego,
- informację o blokadzie konta,
- domyślny projekt dla zadań.

### FR-ACC-003 — Logowanie i wylogowanie

System musi umożliwiać logowanie i wylogowanie użytkownika z użyciem sesji Django.

### FR-ACC-004 — Blokada konta

System musi blokować dostęp użytkownikowi, którego profil ma ustawioną blokadę.

### FR-ACC-005 — Limity logowania

System musi ograniczać liczbę prób logowania zgodnie ze zmiennymi:

- `LOGIN_RATE_LIMIT_ATTEMPTS`,
- `LOGIN_RATE_LIMIT_WINDOW_SECONDS`.

## 4.2 Dashboard

### FR-DASH-001 — Dashboard zależny od roli

System musi prezentować dashboard dopasowany do roli użytkownika.

### FR-DASH-002 — Widget timera

Dla pracownika i managementu system musi pokazywać panel timera umożliwiający rozpoczęcie, pauzę, wznowienie i zakończenie pracy.

### FR-DASH-003 — Widok klienta

Dla klienta dashboard nie może pokazywać danych rozliczeniowych pracowników ani wewnętrznego statusu pracy.

## 4.3 Projekty

### FR-PROJ-001 — Lista projektów

System musi wyświetlać listę projektów widocznych dla użytkownika.

Widoczność projektów:

- management widzi wszystkie projekty,
- klient widzi projekty, gdzie jest klientem lub przypisanym użytkownikiem w roli klienta,
- pracownik widzi projekty, do których jest przypisany.

### FR-PROJ-002 — Tworzenie i edycja projektów

Management musi mieć możliwość tworzenia i edycji projektów.

Projekt musi zawierać:

- nazwę,
- opis,
- klienta,
- status,
- stawkę klienta,
- walutę stawki klienta.

### FR-PROJ-003 — Przypisania projektowe

Management musi móc przypisywać użytkowników do projektów w rolach:

- klient,
- pracownik,
- lead.

### FR-PROJ-004 — Stawki etykiet

Management musi móc definiować stawki dla etykiet zadań w projekcie.

Jeżeli zadanie ma etykietę z przypisaną stawką, raport klienta powinien użyć tej stawki zamiast domyślnej stawki projektu.

## 4.4 Zadania i Kanban

### FR-TASK-001 — Tablica projektu

System musi prezentować zadania projektu w kolumnach Kanban.

### FR-TASK-002 — Domyślne kolumny

System musi tworzyć domyślne kolumny dla projektu, jeśli projekt nie ma jeszcze skonfigurowanej tablicy.

### FR-TASK-003 — Zarządzanie kolumnami

Management musi móc:

- dodawać kolumny,
- edytować nazwy kolumn,
- usuwać puste kolumny,
- oznaczać jedną kolumnę jako kolumnę zakończoną,
- konfigurować uprawnienia kolumn.

### FR-TASK-004 — Uprawnienia kolumn

Kolumna musi obsługiwać oddzielne uprawnienia dla klienta, pracownika i leada:

- widoczność kolumny,
- tworzenie zadań,
- przenoszenie zadań do kolumny,
- edycja zadań,
- usuwanie zadań.

### FR-TASK-005 — Zadanie

Zadanie musi zawierać:

- projekt,
- kolumnę,
- tytuł,
- opis,
- przypisaną osobę lub wiele osób,
- termin,
- priorytet,
- etykiety,
- wyróżnienie gwiazdką,
- kolor karty,
- autora,
- daty utworzenia i aktualizacji.

### FR-TASK-006 — Przenoszenie zadań

System musi pozwalać przenosić zadania między kolumnami, jeżeli użytkownik ma odpowiednie uprawnienie.

### FR-TASK-007 — Notatki edycji

System musi umożliwiać dodawanie notatek przy edycji zadania.

### FR-TASK-008 — Załączniki zadań

System musi umożliwiać dodawanie załączników do zadania oraz linkowanie istniejących dokumentów.

### FR-TASK-009 — Powiadomienia zadań

System musi wysyłać powiadomienia zgodnie z ustawieniami kolumn:

- do przypisanych osób,
- do klientów projektu,
- przy utworzeniu zadania,
- przy dodaniu notatki,
- przy przeniesieniu zadania do określonej kolumny.

## 4.5 Worklogi zadań

### FR-WORKLOG-001 — Dodawanie worklogów

Pracownik musi móc dodać wpis godzin do zadania.

Worklog musi zawierać:

- zadanie,
- użytkownika,
- liczbę godzin,
- datę,
- komentarz,
- informację, czy wpis jest widoczny dla klienta.

### FR-WORKLOG-002 — Widoczność dla klienta

System musi ukrywać przed klientem worklogi oznaczone jako niewidoczne.

### FR-WORKLOG-003 — Edycja worklogów

Pracownik może edytować własny worklog do końca pierwszego dnia następnego miesiąca.

Management może edytować worklog do końca miesiąca, którego dotyczy wpis.

### FR-WORKLOG-004 — Worklogi a payroll

Worklogi zadań nie mogą wpływać na wynagrodzenie pracownika. Payroll pracownika musi być liczony z wpisów czasu pracy, nie z worklogów zadań.

## 4.6 Czas pracy

### FR-TIME-001 — Timer

System musi umożliwiać rozpoczęcie sesji pracy.

Sesja pracy może mieć stan:

- uruchomiona,
- pauza,
- zakończona.

### FR-TIME-002 — Pauza i wznowienie

System musi umożliwiać zapauzowanie i wznowienie aktywnej sesji pracy.

Czas pauzy nie powinien być liczony jako aktywny czas pracy.

### FR-TIME-003 — Zakończenie sesji

Po zakończeniu sesji system musi utworzyć wpis czasu pracy.

### FR-TIME-004 — Nieaktywność

System musi przechowywać czas nieaktywności i odejmować go od aktywnego czasu pracy.

### FR-TIME-005 — Ręczne wpisy czasu

System musi umożliwiać dodawanie ręcznych wpisów czasu pracy.

Wpis czasu musi zawierać:

- użytkownika,
- projekt,
- zadanie,
- datę i godzinę rozpoczęcia,
- datę i godzinę zakończenia,
- źródło,
- komentarz,
- czas nieaktywny,
- informację o edycji.

### FR-TIME-006 — Edycja wpisów czasu

Pracownik może edytować własny wpis czasu do końca pierwszego dnia następnego miesiąca.

Management może edytować wpis czasu do końca miesiąca, którego dotyczy wpis.

## 4.7 Pracownicy i stawki

### FR-EMP-001 — Lista pracowników

Management musi widzieć listę pracowników z podsumowaniem godzin, wynagrodzenia, obciążeń i kwoty do wypłaty.

### FR-EMP-002 — Szczegóły pracownika

Management musi widzieć szczegóły pracownika, w tym:

- dane profilu,
- numer konta bankowego,
- historię stawek,
- wpisy czasu,
- obciążenia,
- podsumowanie rozliczenia.

### FR-EMP-003 — Stawki godzinowe

Management musi móc dodać lub zaktualizować stawkę godzinową pracownika.

Stawka musi zawierać:

- pracownika,
- kwotę,
- walutę,
- datę obowiązywania od,
- opcjonalną datę obowiązywania do,
- autora wpisu.

### FR-EMP-004 — Historia stawek

System musi zachowywać historię stawek i rozliczać wynagrodzenie według stawki obowiązującej w momencie pracy.

### FR-EMP-005 — Automatyczne zamykanie okresów stawek

Po dodaniu nowej stawki system powinien domknąć poprzednią stawkę dzień przed rozpoczęciem nowej.

### FR-EMP-006 — Ograniczenie wstecznej zmiany stawek

Stawkę za poprzedni miesiąc można zmienić najpóźniej do 10. dnia następnego miesiąca.

## 4.8 Obciążenia pracowników

### FR-CHG-001 — Lista obciążeń

System musi posiadać osobną zakładkę obciążeń dostępną dla pracownika i managementu.

Klient nie może mieć dostępu do obciążeń.

### FR-CHG-002 — Obciążenia własne pracownika

Pracownik musi móc dodać obciążenie dla siebie.

### FR-CHG-003 — Obciążenia dodawane przez management

Management musi móc dodać obciążenie dla wybranego pracownika.

### FR-CHG-004 — Dane obciążenia

Obciążenie musi zawierać:

- pracownika,
- nazwę lub rodzaj obciążenia,
- kwotę,
- datę i godzinę przypisania do okresu,
- autora,
- datę utworzenia,
- datę aktualizacji.

### FR-CHG-005 — Znak kwoty

Kwota dodatnia musi pomniejszać wypłatę.

Kwota ujemna musi zwiększać wypłatę.

Przykład: wynagrodzenie `6097,48 PLN`, saldo obciążeń `40,00 PLN`, kwota do wypłaty `6057,48 PLN`.

### FR-CHG-006 — Miesięczne rozliczanie

Obciążenia muszą być rozliczane ręcznie w miesiącu wynikającym z daty obciążenia.

System nie powinien automatycznie powielać obciążeń cyklicznych.

### FR-CHG-007 — Nawigacja po miesiącach

Zakładka obciążeń musi umożliwiać wybór miesiąca oraz przechodzenie do poprzedniego i następnego miesiąca.

### FR-CHG-008 — Filtrowanie managementu

Management musi móc wybrać pracownika w zakładce obciążeń.

Zmiana pracownika powinna odświeżyć dane bez przesuwania użytkownika na początek strony.

### FR-CHG-009 — Termin edycji pracownika

Pracownik może dodać, edytować lub usunąć obciążenie tylko do 5. dnia następnego miesiąca włącznie.

### FR-CHG-010 — Brak limitu dla managementu

Management może dodawać, edytować i usuwać obciążenia bez ograniczenia terminu.

### FR-CHG-011 — Obciążenia w raportach

Raport pracownika i raport payroll muszą uwzględniać:

- wynagrodzenie przed obciążeniami,
- saldo obciążeń,
- kwotę do wypłaty po obciążeniach.

## 4.9 Raporty

### FR-REP-001 — Raport projektowy

System musi generować raport projektowy na podstawie worklogów zadań.

### FR-REP-002 — Raport klienta

Klient musi widzieć tylko worklogi widoczne dla klienta.

Raport klienta powinien liczyć kwoty według:

- stawki etykiety, jeśli zadanie ma etykietę z przypisaną stawką,
- stawki projektu, jeśli brak stawki etykiety.

### FR-REP-003 — Raport managementu

Management musi móc przełączać widoczność raportu między zakresem klienckim i managementowym.

### FR-REP-004 — Raport pracownika

Pracownik musi widzieć raport własnych wpisów czasu i własnego payroll.

### FR-REP-005 — Raport payroll managementu

Management musi widzieć podsumowanie payroll dla jednego lub wielu pracowników.

Podsumowanie musi zawierać:

- godziny,
- wynagrodzenie,
- obciążenia,
- kwotę do wypłaty.

### FR-REP-006 — Eksport CSV

System musi umożliwiać eksport CSV raportów.

Zakres kolumn musi zależeć od roli użytkownika.

### FR-REP-007 — Eksport PDF

System musi umożliwiać eksport PDF/HTML do druku.

Eksport payroll musi zawierać dane do przelewu, jeśli użytkownik ma do nich uprawnienia.

## 4.10 Dokumenty i pliki

### FR-DOC-001 — Dokumenty

System musi umożliwiać tworzenie:

- folderów,
- dokumentów tekstowych,
- plików,
- zdjęć.

### FR-DOC-002 — Hierarchia

Dokumenty muszą obsługiwać strukturę folderów przez relację rodzic-dziecko.

### FR-DOC-003 — Projekty dokumentów

Dokument może być przypisany do projektu.

### FR-DOC-004 — Widoczność dokumentów

System musi wyświetlać dokument użytkownikowi, jeśli:

- jest właścicielem,
- jest przypisany do projektu dokumentu,
- jest klientem projektu,
- ma bezpośredni dostęp,
- jego rola ma dostęp,
- dokument jest powiązany z dostępnym zadaniem.

### FR-DOC-005 — Uprawnienia dokumentów

System musi obsługiwać uprawnienia:

- podgląd,
- edycja,
- zarządzanie.

### FR-DOC-006 — Ukrywanie dokumentów

System musi umożliwiać ukrycie dokumentu przed konkretnym użytkownikiem.

### FR-DOC-007 — Przypięcia

System musi umożliwiać przypięcie dokumentu przez użytkownika.

### FR-DOC-008 — Limity uploadu

System musi walidować:

- maksymalny rozmiar pliku,
- maksymalną liczbę plików użytkownika,
- dozwolone rozszerzenia.

## 4.11 Kalendarz i urlopy

### FR-CAL-001 — Kalendarz pracownika

Pracownik musi widzieć w kalendarzu:

- wpisy czasu pracy,
- terminy zadań,
- własne urlopy.

### FR-CAL-002 — Wnioski urlopowe

Pracownik musi móc złożyć wniosek urlopowy na przyszły okres.

Wniosek musi zawierać:

- użytkownika,
- datę od,
- datę do,
- powód,
- status,
- osobę rozpatrującą,
- datę rozpatrzenia.

### FR-CAL-003 — Decyzje managementu

Management musi móc zaakceptować lub odrzucić wniosek urlopowy.

### FR-CAL-004 — Odczyt decyzji

Pracownik musi móc oznaczyć odrzucony lub rozpatrzony wniosek jako przeczytany.

### FR-CAL-005 — Widok managementu

Management musi widzieć obecność i urlopy pracowników.

## 4.12 Powiadomienia

### FR-NOT-001 — Lista powiadomień

System musi prezentować użytkownikowi listę jego powiadomień.

### FR-NOT-002 — Oznaczanie jako przeczytane

System musi umożliwiać oznaczenie pojedynczego powiadomienia lub wszystkich powiadomień jako przeczytane.

### FR-NOT-003 — Przypomnienia dzienne

System powinien tworzyć dzienne przypomnienia o:

- zadaniach z nadchodzącym terminem,
- urlopach,
- innych istotnych zdarzeniach.

### FR-NOT-004 — Retencja powiadomień

System musi wspierać czyszczenie starych powiadomień zgodnie z konfiguracją retencji.

---

# 5. Wymagania niefunkcjonalne

## 5.1 Bezpieczeństwo

### NFR-SEC-001 — Uwierzytelnianie

System musi wymagać zalogowania do wszystkich widoków aplikacji poza stronami publicznymi, logowaniem i rejestracją.

### NFR-SEC-002 — Hasła

System musi korzystać z mechanizmów hashowania haseł Django.

### NFR-SEC-003 — CSRF

System musi stosować ochronę CSRF dla formularzy modyfikujących dane.

### NFR-SEC-004 — Kontrola dostępu

Każdy widok musi sprawdzać rolę użytkownika i zakres danych, do których ma dostęp.

### NFR-SEC-005 — Dane rozliczeniowe

Numer konta bankowego, stawki godzinowe i payroll nie mogą być widoczne dla klienta.

### NFR-SEC-006 — Produkcja

W środowisku produkcyjnym `DJANGO_DEBUG` musi mieć wartość `false`, a aplikacja powinna działać za HTTPS.

## 5.2 Wydajność

### NFR-PERF-001 — Indeksy

Modele często filtrowane po użytkowniku, projekcie i dacie powinny posiadać indeksy.

### NFR-PERF-002 — Limity list

Raporty i listy powinny ograniczać liczbę jednocześnie renderowanych szczegółowych rekordów tam, gdzie jest to potrzebne dla wydajności.

### NFR-PERF-003 — Cache

System może korzystać z Redis jako backendu cache.

## 5.3 Użyteczność

### NFR-UX-001 — Responsywność

Interfejs powinien być używalny na desktopie, tablecie i urządzeniach mobilnych.

### NFR-UX-002 — Spójność

Formularze, tabele, karty i przyciski powinny używać wspólnego systemu wizualnego.

### NFR-UX-003 — Brak niepotrzebnych przeładowań

Interakcje, które da się obsłużyć lekko po stronie frontendu, powinny zachowywać pozycję użytkownika i nie powodować skoku na początek strony.

## 5.4 Niezawodność

### NFR-REL-001 — Migracje

Zmiany modelu danych muszą być dostarczane przez migracje Django.

### NFR-REL-002 — Testy

Logika biznesowa dotycząca czasu pracy, raportów, stawek, obciążeń i uprawnień powinna być pokryta testami automatycznymi.

### NFR-REL-003 — Integralność danych

System powinien używać ograniczeń bazodanowych tam, gdzie dane muszą być unikalne, np. jedna stawka pracownika dla tej samej daty rozpoczęcia.

## 5.5 Utrzymanie

### NFR-MAINT-001 — Modularność

Kod powinien być podzielony na aplikacje Django odpowiadające modułom biznesowym.

### NFR-MAINT-002 — Konfiguracja

Konfiguracja środowiskowa powinna być przechowywana w zmiennych środowiskowych.

### NFR-MAINT-003 — Dokumentacja

Repozytorium powinno zawierać:

- `README.md` z instrukcją uruchomienia,
- `SRS.md` z wymaganiami systemu.

---

# 6. Reguły biznesowe

## BR-001 — Widoczność danych klienta

Klient widzi tylko dane przypisanych projektów oraz worklogi oznaczone jako widoczne dla klienta.

## BR-002 — Wynagrodzenie pracownika

Wynagrodzenie pracownika jest liczone z wpisów czasu pracy oraz historycznych stawek godzinowych.

Worklogi zadań nie wpływają na payroll pracownika.

## BR-003 — Stawki historyczne

Jeżeli w okresie raportu obowiązywało kilka stawek, system powinien policzyć wynagrodzenie proporcjonalnie według stawek obowiązujących w datach wpisów czasu.

## BR-004 — Stawki wstecz

Stawkę za poprzedni miesiąc można zmienić do 10. dnia następnego miesiąca.

## BR-005 — Edycja wpisów czasu przez pracownika

Pracownik może edytować własny wpis czasu do końca pierwszego dnia następnego miesiąca.

## BR-006 — Edycja wpisów czasu przez management

Management może edytować wpis czasu do końca miesiąca, którego dotyczy wpis.

## BR-007 — Edycja worklogów przez pracownika

Pracownik może edytować własny worklog do końca pierwszego dnia następnego miesiąca.

## BR-008 — Edycja worklogów przez management

Management może edytować worklog do końca miesiąca, którego dotyczy wpis.

## BR-009 — Obciążenia dodatnie

Dodatnia kwota obciążenia pomniejsza wypłatę.

## BR-010 — Obciążenia ujemne

Ujemna kwota obciążenia zwiększa wypłatę.

## BR-011 — Termin obciążeń pracownika

Pracownik może dodać, edytować lub usunąć obciążenie do 5. dnia następnego miesiąca włącznie.

## BR-012 — Obciążenia managementu

Management może zarządzać obciążeniami bez ograniczenia terminu.

## BR-013 — Brak automatycznej cykliczności obciążeń

Obciążenia są wpisywane ręcznie dla konkretnego miesiąca. System nie powiela automatycznie obciążeń miesięcznych.

## BR-014 — Kwota do wypłaty

Kwota do wypłaty jest liczona według wzoru:

```text
kwota_do_wypłaty = wynagrodzenie - saldo_obciążeń
```

## BR-015 — Rozliczanie klienta

W raporcie klienta kwoty mogą być naliczane tylko za pracę widoczną dla klienta, a w wariancie rozliczeniowym tylko za zadania zakończone.

---

# 7. Model danych

## 7.1 Główne encje

| Encja | Opis |
| --- | --- |
| User | Konto Django użytkownika. |
| UserProfile | Rola, numer konta, blokada, domyślny projekt zadań. |
| Project | Projekt, klient, status, stawka klienta. |
| ProjectAssignment | Przypisanie użytkownika do projektu z rolą projektową. |
| ProjectLabelRate | Stawka klienta dla etykiety zadania. |
| BoardColumn | Kolumna Kanban z uprawnieniami i ustawieniami powiadomień. |
| Task | Zadanie w projekcie. |
| TaskEditNote | Notatka edycji zadania. |
| TaskWorklog | Godziny przypisane do zadania. |
| TimeEntry | Wpis czasu pracy używany do payroll. |
| WorkSession | Aktywna lub zakończona sesja timera. |
| HourlyRate | Historyczna stawka godzinowa pracownika. |
| EmployeeCharge | Obciążenie pracownika. |
| DocumentItem | Folder, dokument, plik lub zdjęcie. |
| DocumentAccess | Uprawnienie dostępu do dokumentu. |
| DocumentVisibilityBlock | Ukrycie dokumentu przed użytkownikiem. |
| DocumentPin | Przypięcie dokumentu przez użytkownika. |
| LeaveRequest | Wniosek urlopowy. |
| Notification | Powiadomienie użytkownika. |

## 7.2 Relacje kluczowe

- `User` ma jeden `UserProfile`.
- `Project` może mieć jednego klienta i wielu członków przez `ProjectAssignment`.
- `Project` ma wiele kolumn, zadań, dokumentów i stawek etykiet.
- `Task` należy do projektu i kolumny.
- `Task` ma wiele worklogów, notatek i załączników.
- `TimeEntry` należy do użytkownika i opcjonalnie do projektu oraz zadania.
- `HourlyRate` należy do użytkownika.
- `EmployeeCharge` należy do użytkownika i ma autora.
- `DocumentItem` może mieć rodzica, projekt, właściciela i reguły dostępu.
- `LeaveRequest` należy do użytkownika i może być rozpatrzony przez management.
- `Notification` należy do użytkownika.

---

# 8. Interfejsy zewnętrzne

## 8.1 Interfejs użytkownika

System udostępnia interfejs webowy renderowany przez Django templates.

Główne obszary interfejsu:

- landing page,
- logowanie i rejestracja,
- dashboard,
- projekty,
- Kanban,
- czas pracy,
- worklogi,
- pracownicy,
- obciążenia,
- raporty,
- dokumenty,
- kalendarz,
- powiadomienia,
- ustawienia konta.

## 8.2 Interfejs administratora

System korzysta z panelu Django Admin pod adresem:

```text
/admin/
```

Dostęp do panelu administracyjnego powinien mieć wyłącznie superuser.

## 8.3 Baza danych

System używa PostgreSQL jako głównej bazy danych.

Połączenie jest konfigurowane przez:

```text
DATABASE_URL
```

## 8.4 Cache

System może używać Redis jako backendu cache.

Połączenie jest konfigurowane przez:

```text
REDIS_URL
```

## 8.5 Pliki

Pliki użytkowników są zapisywane w lokalnym storage Django w katalogu mediów.

Pliki statyczne są obsługiwane przez Django/WhiteNoise.

---

# 9. Przypadki użycia

## UC-001 — Rejestracja i logowanie

**Aktor:** użytkownik

**Opis:** użytkownik tworzy konto lub loguje się do istniejącego konta.

**Warunek początkowy:** użytkownik nie jest zalogowany.

**Scenariusz główny:**

1. Użytkownik otwiera formularz logowania lub rejestracji.
2. Podaje wymagane dane.
3. System waliduje dane.
4. System tworzy konto albo loguje użytkownika.
5. System przekierowuje użytkownika do aplikacji.

**Warunek końcowy:** użytkownik jest zalogowany.

## UC-002 — Utworzenie projektu

**Aktor:** management

**Scenariusz główny:**

1. Management otwiera moduł projektów.
2. Wypełnia formularz projektu.
3. Przypisuje klienta i pracowników.
4. System zapisuje projekt.
5. System udostępnia projekt właściwym użytkownikom.

## UC-003 — Praca z zadaniem Kanban

**Aktor:** klient, pracownik, management

**Scenariusz główny:**

1. Użytkownik otwiera tablicę projektu.
2. System pokazuje kolumny zgodne z uprawnieniami użytkownika.
3. Użytkownik tworzy, edytuje lub przenosi zadanie.
4. System sprawdza uprawnienia kolumny.
5. System zapisuje zmianę.
6. System wysyła powiadomienia, jeśli konfiguracja kolumny tego wymaga.

## UC-004 — Rejestracja czasu pracy timerem

**Aktor:** pracownik

**Scenariusz główny:**

1. Pracownik uruchamia timer.
2. System tworzy sesję pracy.
3. Pracownik może zapauzować lub wznowić sesję.
4. Pracownik kończy sesję.
5. System tworzy wpis czasu pracy.
6. Wpis jest dostępny w raportach payroll.

## UC-005 — Dodanie worklogu do zadania

**Aktor:** pracownik

**Scenariusz główny:**

1. Pracownik wybiera zadanie.
2. Dodaje liczbę godzin, datę i komentarz.
3. Ustawia widoczność wpisu dla klienta.
4. System zapisuje worklog.
5. Worklog pojawia się w raportach projektowych.

## UC-006 — Dodanie obciążenia

**Aktor:** pracownik lub management

**Scenariusz główny:**

1. Użytkownik otwiera zakładkę obciążeń.
2. Wybiera miesiąc.
3. Management może wybrać pracownika.
4. Użytkownik wpisuje rodzaj, kwotę i datę.
5. System sprawdza termin edycji.
6. System zapisuje obciążenie.
7. System aktualizuje saldo i kwotę do wypłaty.

## UC-007 — Wygenerowanie raportu payroll

**Aktor:** pracownik lub management

**Scenariusz główny:**

1. Użytkownik otwiera raporty.
2. Wybiera okres.
3. Management może wybrać pracownika, klienta lub projekt.
4. System pobiera wpisy czasu.
5. System oblicza wynagrodzenie według stawek historycznych.
6. System pobiera obciążenia.
7. System wylicza kwotę do wypłaty.
8. Użytkownik może wyeksportować raport.

## UC-008 — Obsługa dokumentów

**Aktor:** użytkownik z dostępem

**Scenariusz główny:**

1. Użytkownik otwiera moduł dokumentów.
2. Tworzy folder, dokument tekstowy lub uploaduje plik.
3. System waliduje limity uploadu.
4. Użytkownik ustawia projekt lub dostęp.
5. System zapisuje dokument i respektuje reguły widoczności.

## UC-009 — Wniosek urlopowy

**Aktor:** pracownik, management

**Scenariusz główny:**

1. Pracownik tworzy wniosek urlopowy.
2. System wysyła powiadomienie do managementu.
3. Management akceptuje lub odrzuca wniosek.
4. System zapisuje decyzję.
5. Pracownik widzi status w kalendarzu.

---

# 10. Kryteria akceptacji

## 10.1 Konta

- Użytkownik może się zarejestrować i zalogować.
- Użytkownik zablokowany nie może korzystać z aplikacji.
- Rola użytkownika wpływa na widoczność modułów.

## 10.2 Projekty i Kanban

- Management widzi wszystkie projekty.
- Pracownik widzi tylko przypisane projekty.
- Klient widzi tylko swoje projekty.
- Zadania można tworzyć, edytować i przenosić zgodnie z uprawnieniami kolumn.
- Projekt może mieć tylko jedną kolumnę oznaczoną jako zakończona.

## 10.3 Czas pracy i worklogi

- Timer tworzy poprawny wpis czasu po zakończeniu pracy.
- Pauza i nieaktywność nie zwiększają aktywnych godzin pracy.
- Pracownik nie może edytować wpisów po terminie.
- Worklog niewidoczny dla klienta nie pojawia się klientowi.
- Worklogi nie wpływają na payroll pracownika.

## 10.4 Pracownicy, stawki i obciążenia

- Historyczne stawki są zachowywane.
- Payroll uwzględnia stawki obowiązujące w czasie pracy.
- Obciążenie dodatnie zmniejsza kwotę do wypłaty.
- Obciążenie ujemne zwiększa kwotę do wypłaty.
- Pracownik nie może dodać/edytować/usunąć obciążenia po 5. dniu następnego miesiąca.
- Management może zarządzać obciążeniami bez limitu terminu.

## 10.5 Raporty

- Raport pracownika pokazuje własne godziny, payroll, obciążenia i kwotę do wypłaty.
- Raport managementu pokazuje podsumowanie dla pracowników.
- Raport klienta nie ujawnia danych wewnętrznych.
- Eksport CSV działa dla dostępnego zakresu raportu.
- Eksport PDF zawiera poprawne podsumowania.

## 10.6 Dokumenty i urlopy

- Dokumenty są widoczne tylko dla uprawnionych użytkowników.
- Upload odrzuca niedozwolone rozszerzenia.
- Pracownik może złożyć wniosek urlopowy na przyszłość.
- Management może zaakceptować lub odrzucić urlop.

---

# 11. Środowisko i uruchomienie

## 11.1 Wymagania

Do uruchomienia lokalnego wymagane są:

- Docker,
- Docker Compose,
- opcjonalnie `make`.

## 11.2 Plik środowiskowy

Przed uruchomieniem należy utworzyć plik `.env` na podstawie `.env.example`.

```bash
cp .env.example .env
```

Na Windows można skopiować plik ręcznie.

## 11.3 Uruchomienie

```bash
docker compose up -d --build
```

Alternatywnie:

```bash
make rebuild
```

Aplikacja lokalna:

```text
http://127.0.0.1:8000
```

## 11.4 Migracje

Migracje są wykonywane automatycznie przez entrypoint kontenera.

Ręczne wykonanie:

```bash
docker compose exec web python manage.py migrate
```

## 11.5 Superuser

```bash
docker compose exec web python manage.py createsuperuser
```

## 11.6 Testy

```bash
docker compose exec web python manage.py test
```

## 11.7 Sprawdzenie konfiguracji

```bash
docker compose exec web python manage.py check
```

## 11.8 Kluczowe zmienne środowiskowe

| Zmienna | Opis |
| --- | --- |
| `DJANGO_SECRET_KEY` | Sekretny klucz Django. |
| `DJANGO_DEBUG` | Tryb debugowania. |
| `DJANGO_ALLOWED_HOSTS` | Dozwolone hosty. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Zaufane originy CSRF. |
| `DATABASE_URL` | Połączenie z PostgreSQL. |
| `REDIS_URL` | Połączenie z Redis. |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | Limit prób logowania. |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | Okno limitu logowania. |
| `DOCUMENTS_MAX_UPLOAD_SIZE_BYTES` | Maksymalny rozmiar pliku. |
| `DOCUMENTS_MAX_FILES_PER_USER` | Maksymalna liczba plików użytkownika. |
| `DOCUMENTS_ALLOWED_UPLOAD_EXTENSIONS` | Dozwolone rozszerzenia. |
| `NOTIFICATIONS_PER_PAGE` | Liczba powiadomień na stronę. |
| `NOTIFICATIONS_READ_RETENTION_DAYS` | Retencja przeczytanych powiadomień. |
| `NOTIFICATIONS_UNREAD_RETENTION_DAYS` | Retencja nieprzeczytanych powiadomień. |

---

# 12. Zakres poza projektem

Aktualny zakres nie obejmuje:

- integracji z bankiem,
- automatycznych przelewów,
- fakturowania,
- pełnego systemu księgowego,
- aplikacji mobilnej,
- integracji z zewnętrznymi kalendarzami,
- osobnego frontendu SPA,
- płatności online,
- pełnego audytu każdej zmiany w systemie,
- automatycznego powielania cyklicznych obciążeń.

---

# 13. Słownik pojęć

| Pojęcie | Definicja |
| --- | --- |
| Payroll | Rozliczenie wynagrodzenia pracownika za wybrany okres. |
| Obciążenie | Kwota wpływająca na wypłatę pracownika; dodatnia pomniejsza wypłatę, ujemna ją zwiększa. |
| Worklog | Wpis godzin przypisany do zadania, używany w raportach projektowych. |
| Time entry | Wpis czasu pracy używany do rozliczenia wynagrodzenia. |
| Kanban | Widok zadań w kolumnach reprezentujących etap pracy. |
| Kolumna zakończona | Kolumna oznaczająca zakończone zadania, używana m.in. w raportach klienta. |
| Management | Rola administracyjna w aplikacji biznesowej. |
| Lead | Rola projektowa użytkownika z rozszerzonymi uprawnieniami w projekcie. |
| Widoczność dla klienta | Flaga określająca, czy dany worklog może być pokazany klientowi. |
| Stawka etykiety | Stawka klienta przypisana do etykiety zadania. |
| Stawka historyczna | Stawka godzinowa pracownika obowiązująca w konkretnym okresie. |
