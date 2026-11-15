# TeamTalk runtime / Środowisko TeamTalk

The TeamTalk SDK is a separate BearWare product. Its wrapper, native libraries,
and registration keys are not redistributed in this repository and are not
covered by this project's MIT license.

1. Read the [official SDK information](https://bearware.dk/?page_id=419).
2. Run `python3 tools/fetch_teamtalk_wrapper.py` from the repository root to
   download the official v5.23 Python wrapper with SHA-256 verification.
3. Obtain a compatible native library for your operating system and architecture.
   The tested Linux combination is wrapper v5.23 and `libTeamTalk5.so` v5.23
   for Ubuntu 24 x86_64, available in the
   [official TeamTalk distribution](https://bearware.dk/?page_id=353).
4. Put `libTeamTalk5.so` here and configure your own SDK registration name and key.
5. Keep the applicable BearWare license with your local SDK installation.

SDK TeamTalk jest osobnym produktem BearWare. Wrapper, biblioteki natywne i klucze
rejestracyjne nie są rozpowszechniane w tym repozytorium i nie podlegają licencji MIT projektu.

1. Zapoznaj się z [informacjami o SDK](https://bearware.dk/?page_id=419).
2. W katalogu projektu uruchom `python3 tools/fetch_teamtalk_wrapper.py`.
   Skrypt pobierze oficjalny wrapper v5.23 i sprawdzi sumę SHA-256.
3. Pobierz zgodną bibliotekę dla swojego systemu i architektury.
   Przetestowano wrapper v5.23 i `libTeamTalk5.so` v5.23 dla Ubuntu 24 x86_64
   z [oficjalnej dystrybucji TeamTalk](https://bearware.dk/?page_id=353).
4. Umieść `libTeamTalk5.so` w tym katalogu i podaj własne dane licencji SDK.
5. Zachowaj odpowiednią licencję BearWare w swojej lokalnej instalacji SDK.
