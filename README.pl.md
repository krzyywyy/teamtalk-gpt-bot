# TeamTalk GPT Bot

[![Testy](https://github.com/krzyywyy/teamtalk-gpt-bot/actions/workflows/tests.yml/badge.svg)](https://github.com/krzyywyy/teamtalk-gpt-bot/actions/workflows/tests.yml)
![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)
[![Licencja MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[English](README.md) · **Polski**

Asystent tekstowy dla serwerów TeamTalk, korzystający z OpenAI Responses API.
Napisz do bota prywatnie albo na kanale, na którym przebywa, a otrzymasz odpowiedź.
Domyślny model to **GPT-6 Luna** (`gpt-6-luna`); można go zmienić w konfiguracji.

Projekt jest przygotowany do pracy na serwerze Linux: ma automatyczne wznawianie połączenia,
usługę systemd, ograniczoną kolejkę zapytań, rotację logów i prywatny status dla administratorów.

## Możliwości

- Automatyczne odpowiedzi na wiadomości prywatne i wiadomości w aktualnym kanale bota.
- Osobny kontekst dla każdego użytkownika oraz dla rozmów prywatnych i kanałowych.
- Odpowiedzi w języku wiadomości, w prostym tekście odpowiednim dla czytników ekranu.
- `/status` tylko dla administratorów serwera TeamTalk; wynik zawsze prywatnie.
- `/channel on`, `/channel off` i `/channel status` dla administratorów w wiadomościach prywatnych.
- Opcjonalny rzeczywisty koszt miesięczny w USD z OpenAI Costs API, widoczny w statusie administratora.
- `/reset` do usunięcia kontekstu rozmowy oraz `/help` z krótką pomocą.
- Dzielenie i składanie wiadomości UTF-8, również z polskimi znakami i emoji.
- Dwa równoległe zapytania do API, zachowanie kolejności w obrębie rozmowy i limity częstotliwości.
- Ponowne łączenie z odstępami od 3 do 60 sekund, poprawne zamykanie i autostart przez systemd.
- Logi i plik statusu bez treści wiadomości oraz danych dostępowych.
- Wyłącznie standardowa biblioteka Pythona; bot i testy nie wymagają pakietów pip.

Bot obsługuje tekst. Nie słucha dźwięku, nie mówi, nie przegląda internetu i nie wykonuje poleceń
systemowych. Przy włączonych odpowiedziach kanałowych (domyślnie) odpowiada na
**wszystkie wiadomości w swoim aktualnym kanale**, bez wymogu wzmianki.
Nie obserwuje jednocześnie wszystkich kanałów serwera. Lokalne komunikaty pomocy i błędów są
obecnie po polsku, odpowiedzi modelu zależą od języka użytkownika, a raport `/status` jest po angielsku.

## Wymagania

- Python **3.12 lub nowszy**.
- Linux ze zgodną biblioteką natywną TeamTalk; sprawdzono Ubuntu 24 x86_64.
- Konto TeamTalk z prawem do wyświetlania użytkowników, wejścia do wybranego kanału
  i wysyłania wiadomości prywatnych oraz kanałowych.
- Własny klucz API OpenAI z dostępem do wybranego modelu i środkami na zapytania.
- Własne, poprawne **dane rejestracyjne i klucz licencji SDK TeamTalk firmy BearWare**.

Sprawdzony zestaw to TeamTalk v5.23 oraz wrapper Pythona v5.23.
Wystarczy zwykłe konto bota z odpowiednimi uprawnieniami; bot nie musi być administratorem serwera.
Komenda `/status` sprawdza uprawnienia administratora osoby, która ją wysłała.

## Szybki start

### 1. Pobierz projekt i wrapper

```sh
git clone https://github.com/krzyywyy/teamtalk-gpt-bot.git
cd teamtalk-gpt-bot
python3 tools/fetch_teamtalk_wrapper.py
```

Skrypt pobiera oficjalny wrapper w ustalonej wersji i weryfikuje jego sumę SHA-256.
Nie pobiera ani nie udostępnia klucza licencji. Szczegóły są w [instrukcji środowiska TeamTalk](vendor/README.md).

### 2. Zainstaluj bibliotekę natywną TeamTalk

Pobierz zgodną bibliotekę Linux ze strony [BearWare](https://bearware.dk/?page_id=419)
albo z [oficjalnej dystrybucji TeamTalk](https://bearware.dk/?page_id=353), zgodnie
z właściwą licencją SDK. Umieść `libTeamTalk5.so` w katalogu `vendor/`:

```sh
cp /sciezka/do/libTeamTalk5.so vendor/
ldd vendor/libTeamTalk5.so
```

Zainstaluj brakujące zależności systemowe wskazane przez `ldd`. Dobierz bibliotekę do systemu
i architektury procesora. Wersja z nowszej dystrybucji Linux może wymagać nowszej biblioteki glibc.

### 3. Wpisz własne dane

```sh
cp .env.example .env
chmod 600 .env
```

Edytuj `.env`: uzupełnij klucz OpenAI, domenę i porty TeamTalk, dane konta
oraz rejestrację SDK BearWare. Domena `teamtalk.example.com` i dane w przykładzie
są zastępcze. Użyj rzeczywistych portów TCP/UDP i ustawienia szyfrowania swojego serwera.

### 4. Sprawdź i uruchom

```sh
python3 -m unittest discover -s tests -v
LD_LIBRARY_PATH="$PWD/vendor" python3 -m tt_gpt --env .env --check
LD_LIBRARY_PATH="$PWD/vendor" python3 -m tt_gpt --env .env
```

`--check` sprawdza licencję SDK i zgodność struktur C/Python, a następnie wykonuje
krótkie zapytanie do OpenAI. **Nie łączy się z TeamTalk** i może naliczyć niewielką opłatę API.
Zwykłe uruchomienie loguje bota, ustawia pseudonim/status i dołącza do wybranego kanału.
Proces uruchomiony w terminalu zatrzymasz przez Ctrl+C.

## Konfiguracja

Ustawienia pochodzą ze zmiennych środowiskowych albo z pliku wskazanego przez `--env`.
Zmienne już obecne w środowisku procesu mają pierwszeństwo przed plikiem `--env`.
Plik zawiera dosłowne wiersze `KLUCZ=wartość`; nie wykonuje poleceń powłoki.

| Zmienna | Znaczenie | Wartość domyślna / przykład |
| --- | --- | --- |
| `OPENAI_API_KEY` | Własny klucz API OpenAI | Wymagana |
| `OPENAI_MODEL` | Model Responses API | `gpt-6-luna` |
| `OPENAI_ADMIN_KEY` | Opcjonalny klucz Admin API do rzeczywistych kosztów miesięcznych | Pusta; rozmowy działają bez niego |
| `OPENAI_COST_PROJECT_ID` | Opcjonalny filtr projektu dla Costs API | Pusta = cała organizacja |
| `TT_HOST` | Domena serwera TeamTalk | `teamtalk.example.com` |
| `TT_TCP_PORT` | Port TCP TeamTalk | `10333` |
| `TT_UDP_PORT` | Port UDP TeamTalk | `10333` |
| `TT_ENCRYPTED` | Czy serwer korzysta z szyfrowanego połączenia TeamTalk | `false` |
| `TT_USERNAME` | Nazwa konta bota | Wymagana |
| `TT_PASSWORD` | Hasło konta bota | Wymagana |
| `TT_PASSWORD_FALLBACK` | Opcjonalne drugie hasło, sprawdzane po odrzuceniu pierwszego | Pusta |
| `TT_LICENSE_NAME` | Nazwa rejestracyjna SDK BearWare | Wymagana |
| `TT_LICENSE_KEY` | Klucz licencji SDK BearWare | Wymagana |
| `TT_NICKNAME` | Widoczny pseudonim | `Chat GPT` |
| `TT_STATUS` | Widoczny opis statusu | `If you need help, send me a message.` |
| `TT_CHANNEL` | Ścieżka kanału po zalogowaniu lub ponownym połączeniu | `/` |
| `TT_CHANNEL_PASSWORD` | Hasło wybranego kanału | Pusta |
| `BOT_DATA_DIR` | Katalog logów i pliku statusu | `data` przy pracy ręcznej |

Administrator może przenieść bota do innego kanału. Bot odpowiada tam do czasu
ponownego połączenia lub restartu; wtedy wraca do `TT_CHANNEL`.

## Komendy na czacie

| Komenda | Kto może używać? | Działanie |
| --- | --- | --- |
| `/help` | Każdy | Prywatna wiadomość z krótką pomocą. |
| `/reset` | Każdy | Usuwa kontekst rozmowy, w której jej użyto, oraz odrzuca oczekujące i przetwarzane dla niej wyniki. Potwierdzenie jest prywatne. |
| `/status` | Administratorzy serwera | Stan połączenia, tryb odpowiedzi kanałowych, model, czas działania, kolejki, liczniki, ostatni błąd i opcjonalnie rzeczywiste zgłoszone koszty w USD. Zawsze prywatnie. |
| `/channel off` | Administratorzy serwera, tylko na PW | Wyłącza odpowiedzi kanałowe, usuwa oczekujące zapytania/odpowiedzi kanałowe i odrzuca wyniki już przetwarzanych zapytań. Wiadomości prywatne nadal działają. |
| `/channel on` | Administratorzy serwera, tylko na PW | Ponownie włącza odpowiedzi kanałowe. |
| `/channel status` | Administratorzy serwera, tylko na PW | Pokazuje aktualny tryb odpowiedzi kanałowych. Samo `/channel` również pokazuje tę informację. |

Uprawnienia są odczytywane z flagi `USERTYPE_ADMIN` w SDK, a nie z pseudonimu
lub deklaracji użytkownika. Sam operator kanału nie jest administratorem serwera.
Liczniki tokenów dotyczą bieżącego procesu bota. Tryb odpowiedzi kanałowych jest zapisywany
atomowo w `BOT_DATA_DIR/settings.json` i pozostaje po ponownym połączeniu, restarcie procesu i serwera.
Komenda sterująca wysłana publicznie nie zmienia ustawienia. Zapytanie już wysłane do OpenAI
może zostać naliczone po wyłączeniu kanału; jego odpowiedź nie zostanie wysłana na kanał.

### Rzeczywisty koszt USD w `/status`

Dodaj `OPENAI_ADMIN_KEY` do prywatnego pliku konfiguracji, aby włączyć odczyt
z [OpenAI Costs API](https://platform.openai.com/docs/api-reference/usage/costs).
Status administratora pokazuje **koszt zgłoszony dla organizacji od początku bieżącego
miesiąca kalendarzowego w UTC**. To kwota z API rozliczeń, a nie szacunek na podstawie cen tokenów.
Domyślnie obejmuje wszystkie projekty i aplikacje organizacji, nie tylko tego bota.
`OPENAI_COST_PROJECT_ID` pozwala ograniczyć raport do jednego projektu; obejmuje on wtedy
także inne aplikacje działające w tym projekcie.

Raport jest pobierany w osobnym wątku przy starcie, a następnie odświeżany przy komendach statusu
z pięciominutową pamięcią podręczną. Błąd rozliczeń lub sieci nie blokuje TeamTalk ani rozmów.
Raport podaje czas pobrania, a dane OpenAI mogą być opóźnione. Pusty raport oznacza, że dla
wybranego okresu nie zgłoszono jeszcze kosztów. Nieudane odświeżenie oznacza zachowany raport jako nieaktualny.

Costs API **nie podaje pozostałego salda przedpłaconych środków**. Bot pokazuje brak dostępu
do tej wartości i nie zgaduje salda. Zwykłe rozmowy nie wymagają klucza Admin API.
Klucz pozostaje poza historią rozmów, logami i repozytorium Git.

## Instalacja jako usługa systemd

Najpierw skonfiguruj pliki SDK. W katalogu pobranego projektu wykonaj:

```sh
sudo sh deploy/install.sh
sudoedit /etc/teamtalk-gpt-bot/bot.env
sudo systemctl enable --now tt-gpt
```

Instalator tworzy osobne konto systemowe `tt-gpt` i umieszcza aplikację
w `/opt/teamtalk-gpt-bot`. Jeśli konfiguracji jeszcze nie ma, tworzy szablon
z prawami `0600`. Zachowuje istniejącą konfigurację i zostawia uruchomienie usługi
ostatniej komendzie powyżej. Nie kopiuje automatycznie pliku `.env` z katalogu źródłowego.

Usługa czyta `/etc/teamtalk-gpt-bot/bot.env`. Wpisz tam rzeczywiste ustawienia.
Zostaw `BOT_DATA_DIR` nieustawione w tym pliku, aby użyć katalogu danych usługi:
`/var/lib/teamtalk-gpt-bot`. Usługa ogranicza zapis do systemu plików, pracuje bez praw roota
i wyłącza niepotrzebne wykrywanie sprzętu audio dla bota tekstowego.

```sh
sudo systemctl status tt-gpt
sudo systemctl restart tt-gpt
sudo systemctl stop tt-gpt
sudo journalctl -u tt-gpt -n 100 --no-pager
sudo tail -n 100 /var/lib/teamtalk-gpt-bot/logs/bot.log
sudo cat /var/lib/teamtalk-gpt-bot/status.json
```

Po zmianie konfiguracji zrestartuj usługę. Przy aktualizacji pobierz przejrzane zmiany,
ponownie wykonaj `sudo sh deploy/install.sh`, a następnie zrestartuj `tt-gpt`.
Błędna konfiguracja konta, kanału lub licencji może zakończyć bota kodem **78**.
systemd nie ponawia bez końca procesu z tym kodem; popraw konfigurację i uruchom go ponownie.
Inne awarie procesu powodują restart, a chwilowe zerwanie połączenia TeamTalk obsługuje sam bot.

## Prywatność, logi i limity

- Żądania trafiają do API OpenAI z `store=false`; nadal obowiązują zasady przetwarzania danych OpenAI.
- Historia jest w RAM: maksymalnie sześć ostatnich par pytań i odpowiedzi, ograniczenie do około
  24000 znaków i usuwanie po 30 minutach bez zakończonej wymiany wiadomości.
- Rozmowy prywatne i kanałowe mają oddzielne konteksty, osobne dla każdego użytkownika.
  Wylogowanie usuwa kontekst użytkownika; restart usuwa całą historię.
- Logi zawierają zdarzenia działania oraz numeryczne identyfikatory użytkowników i kanałów,
  ale nie treść wiadomości, klucze API, hasła ani klucze rejestracyjne SDK.
  Pliki mają do 2 MB i pięć kopii zapasowych.
- `status.json` jest odświeżany mniej więcej co 10 sekund i zawiera dane o działaniu bota.
  Przy włączonych rozliczeniach zawiera również zapamiętany raport kosztów; chroń katalog danych.
- Limity API: 8000 znaków na pytanie, 10 pytań na minutę na użytkownika,
  30 pytań na minutę łącznie, dwa równoległe zapytania i do 24 oczekujących/przetwarzanych zapytań.
- Komendy mają osobny limit 10/min na użytkownika. Ponowienia API są ograniczone;
  błędy braku środków nie powodują ponowień. Odpowiedź ma do 1800 tokenów wyjściowych i 7000 znaków.

Limity częstotliwości nie ustanawiają limitu wydatków. Ustaw odpowiedni budżet w projekcie OpenAI.
Nie dodawaj prawdziwej konfiguracji do repozytorium: `.env`, `.secrets/`, dane działania i pliki SDK są ignorowane.

## Rozwiązywanie problemów

| Objaw | Co sprawdzić |
| --- | --- |
| Nie można załadować `libTeamTalk5.so` | Plik w `vendor/`, ustawienie `LD_LIBRARY_PATH` i brak brakujących zależności w `ldd`. |
| SDK odrzuca licencję | Własne poprawne dane rejestracyjne BearWare oraz zgodna edycja/wersja SDK. |
| Błąd TeamTalk `2002` | Nazwa konta, hasło i dostępność konta na wybranym serwerze. |
| Bot jest online, ale nie odpowiada niektórym osobom | Uprawnienia konta do wyświetlania użytkowników i wysyłania wiadomości prywatnych/kanałowych. |
| Brak odpowiedzi na kanale | Obecność bota w tym kanale i prawo wysyłania wiadomości kanałowych. |
| `model_not_found` | Identyfikator modelu i dostęp do niego w projekcie API. |
| `insufficient_quota` | Środki i rozliczenia projektu API. |
| Usługa kończy się kodem `78` | Popraw konfigurację, sprawdź logi i zrestartuj usługę. |

## Rozwój projektu

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q tt_gpt tools tests
python3 tools/check_public_files.py
```

43 testy korzystają z atrap odpowiedzi API i obiektów SDK, więc nie wymagają kluczy,
biblioteki natywnej ani działającego serwera. GitHub Actions uruchamia je na Linux
i Windows z Pythonem 3.12 oraz 3.13. Sprawdza również śledzone pliki pod kątem
typowych wzorców kluczy i prywatnych ścieżek. Ten skan pomaga wyłapać pomyłki,
ale nie zastępuje przeglądu zmian przed publikacją.

```text
tt_gpt/     Konfiguracja, klient Responses API, kolejka zapytań i obsługa TeamTalk
tests/      Testy kierowania wiadomości, uprawnień, prywatności, błędów, limitów i fragmentów
deploy/     Ogólny instalator Linux, usługa systemd i konfiguracja bez sprzętu audio
tools/      Pobieranie oficjalnego wrappera i sprawdzanie plików repozytorium
vendor/     Lokalne pliki TeamTalk; śledzona jest wyłącznie instrukcja instalacji
```

## Licencja i wykorzystane projekty

Oryginalny kod bota jest udostępniony na [licencji MIT](LICENSE).
**SDK TeamTalk jest osobnym produktem BearWare i nie podlega licencji MIT tego projektu.**
Wrapper i biblioteki natywne instaluje się osobno; repozytorium ich nie rozpowszechnia.

- [SDK TeamTalk i informacje o licencji](https://bearware.dk/?page_id=419)
- [Oficjalny wrapper TeamTalk dla Pythona](https://github.com/BearWare/TeamTalk5/tree/v5.23/Library/TeamTalkPy)
- [OpenAI Responses API](https://developers.openai.com/api/docs/guides/text)
- [Model GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)

To niezależny projekt, a nie oficjalna aplikacja OpenAI lub BearWare.
