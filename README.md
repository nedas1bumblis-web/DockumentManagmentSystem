# Įmonės žinių duomenų bazės valdymo sistema

Interneto naršyklėje veikianti sistema: vartotojas įkelia PDF ir DOCX dokumentus, užduoda klausimus lietuvių
arba anglų kalba ir gauna atsakymą su šaltiniu (dokumentas ir puslapis). Atsakymus generuoja Google Gemini
pagal ištraukas, rastas tik paties vartotojo pasirinktuose dokumentuose (RAG).

Sistema naudojama tik per naršyklę (kompiuteryje). Mobiliosios programėlės nėra.

## Paleidimas auditorijoje – instrukcija kursiokui

Tavo kompiuteris auditorijoje bus **serveris**: jame veiks sistema, o kiti kursiokai ją atidarys savo naršyklėse
adresu `https://<tavo kompiuterio IP>`. Jiems nieko diegti nereikia. Viską paruošia vienas skriptas
`paleisti_auditorijoje.ps1`.

> Svarbiausia: **1 dalį atlik iš anksto namuose.** Ten reikia interneto, administratoriaus teisių ir kompiuterio
> perkrovimo, o pirmas paleidimas atsisiunčia ~1 GB. Auditorijoje lieka tik 2 dalis (~2 min.).

### Ko reikia

- Windows 10 arba 11 nešiojamas kompiuteris su administratoriaus teisėmis, bent 8 GB RAM, ~5 GB laisvos vietos.
- Projekto aplankas (ZIP, kurį gavai). Išskleisk jį į paprastą vietą, pvz., `C:\DMS`
  (geriausia be tarpų ir lietuviškų raidžių kelyje).

### 1 dalis. Iš anksto, namuose (~30–40 min.)

1. **Python 3.13.** Atsisiųsk iš <https://www.python.org/downloads/> (būtent **3.13.x**, ne 3.14). Diegiant
   **pažymėk „Add python.exe to PATH“**.
2. **Docker Desktop.** Atsisiųsk iš <https://www.docker.com/products/docker-desktop/> ir įdiek su numatytais
   nustatymais (WSL 2). Kai paprašys, **perkrauk kompiuterį**. Tada atidaryk Docker Desktop, sutik su sąlygomis
   (registruotis nebūtina, galima „Skip“) ir palauk, kol apačioje kairėje bus žalia „Engine running“.
3. **Pirmas paleidimas.** Atidaryk meniu Pradėti, surask **Windows PowerShell**, dešiniu pelės mygtuku pasirink
   **„Run as administrator“** ir įvesk (kelią pakeisk, jei išskleidei kitur):
   ```powershell
   cd C:\DMS
   powershell -ExecutionPolicy Bypass -File .\paleisti_auditorijoje.ps1
   ```
   Skriptas pats sukurs Python aplinką, įdiegs paketus, sukurs `.env` su atsitiktiniais slaptažodžiais, paleis
   duomenų bazę, sukurs testines paskyras ir failus, HTTPS ir svetainę. Pirmą kartą tai trunka 10–20 min.
4. Kai pamatysi žalią langelį su adresu, naršyklėje atidaryk <https://localhost>. Naršyklė perspės dėl
   sertifikato: spausk **„Išplėstiniai“ → „Tęsti į localhost“** (Edge: „Išsamiau“ → „Tęsti“). Prisijunk kaip
   `admin@test.lt` / `Admin1234!`. Jei matai „Admin panelė“, viskas veikia.
5. Sustabdyk: PowerShell lange **Ctrl+C**.

**Dirbtinis intelektas (DI).** Be rakto sistema veikia **DI imitacijos** režimu: vietoj sugeneruoto atsakymo
parodoma tinkamiausia dokumento ištrauka su šaltiniu. Visa kita veikia taip pat. Norint tikrų Gemini atsakymų,
reikia nemokamo rakto iš <https://aistudio.google.com/apikey>. Jį paleidžiant įrašyk vieną kartą (jis išsaugomas `.env`):
```powershell
powershell -ExecutionPolicy Bypass -File .\paleisti_auditorijoje.ps1 -GeminiKey "AIza...tavo_raktas"
```
Nemokamas raktas turi užklausų per minutę ribą. Jei visa grupė klausia vienu metu, kai kurie gali gauti
„Dirbtinio intelekto paslauga laikinai nepasiekiama“ – tada reikia palaukti kelias sekundes ir paklausti dar kartą.
Neįkelk privačių dokumentų: nemokamoje versijoje Google gali naudoti turinį (žr. „Privatumas“).

### 2 dalis. Auditorijoje (~2 min.)

1. Prisijunk prie **to paties Wi-Fi tinklo kaip ir kursiokai**. Jungk kompiuterį į elektros lizdą (kad neužmigtų).
2. Paleisk **Docker Desktop** ir palauk „Engine running“.
3. Atidaryk **PowerShell „Run as administrator“** ir paleisk tą patį skriptą:
   ```powershell
   cd C:\DMS
   powershell -ExecutionPolicy Bypass -File .\paleisti_auditorijoje.ps1
   ```
4. Skriptas parodys adresą, pvz., **`https://192.168.1.23`**. Užrašyk jį lentoje arba nusiųsk kursiokams.
5. Kursiokai atidaro tą adresą, praleidžia sertifikato perspėjimą („Išplėstiniai“ → „Tęsti“) ir prisijungia.
6. **Neuždaryk PowerShell lango**, kol vyksta testavimas, ir neužmigdyk kompiuterio.

**Paskyros** (slaptažodžiai vienodi visiems testuotojams):

| Kas | El. paštas | Slaptažodis |
|---|---|---|
| Administratorius | `admin@test.lt` | `Admin1234!` |
| Vartotojai pagal QA scenarijus | `vartotojas1@test.lt`, `vartotojas2@test.lt` | `Test1234!` |
| Kiekvienam kursiokui atskira | `user001@test.lt` … `user100@test.lt` | `Test1234!` |

Geriausia kiekvienam kursiokui duoti atskirą `userNNN` paskyrą, kad jų dokumentai nesimaišytų. Po 5 neteisingų
slaptažodžių paskyra užblokuojama 15 min. Administratorius gali ją atblokuoti: „Admin panelė“ → „Redaguoti“ →
„Atblokuoti“. Testiniai failai QA scenarijams yra aplanke `samples\test_files`. Jei kursiokai juos naudoja savo
kompiuteriuose, nukopijuok jiems šį aplanką.

### Jei kursiokai negali atidaryti adreso

| Ką mato | Ką daryti |
|---|---|
| Ilgai kraunasi, „Svetainė nepasiekiama“ | Skriptas paleistas ne administratoriaus teisėmis, todėl ugniasienė uždaryta: paleisk PowerShell „Run as administrator“ ir skriptą dar kartą. |
| Vis tiek nepasiekiama | Patikrink, ar visi tame pačiame Wi-Fi. Universiteto ir viešuose tinkluose (pvz., eduroam) įrenginiai dažnai negali jungtis vienas prie kito. Tada **įjunk telefono mobilųjį prieigos tašką** ir prie jo prijunk ir savo, ir kursiokų kompiuterius, o skriptą paleisk iš naujo (IP pasikeis). |
| Netinka nė vienas tinklas | Viešas adresas per internetą (Cloudflare Tunnel) – žr. žemiau. |
| Adresas ne toks, kokio tikėjaisi (pvz., `172.x.x.x` iš Docker) | Pažiūrėk tikrą IP komanda `ipconfig` (Wi-Fi adapterio „IPv4 Address“) ir paleisk su `-Ip 192.168.x.x`. |

**Viešas adresas per internetą (Cloudflare Tunnel).** Tinka bet kuriame tinkle, bet adresas pasiekiamas iš viso
interneto, kol tunelis įjungtas. Iš anksto įdiek `cloudflared`
(<https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/>). Auditorijoje paleisk
skriptą kaip įprasta, o **antrame** PowerShell lange:
```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```
Po kelių sekundžių atsiras adresas `https://<atsitiktiniai-žodžiai>.trycloudflare.com`. Duok jį kursiokams.
Sertifikato perspėjimo čia nebus. Baigus – Ctrl+C abiejuose languose.

### Baigus testuoti

- PowerShell lange **Ctrl+C**, tada `docker stop dms-caddy document-managment-system`.
- Duomenys (paskyros, įkelti dokumentai) išlieka, kitą kartą užtenka vėl paleisti skriptą.
- Viską ištrinti: Docker Desktop → Containers → ištrinti `dms-caddy` ir `document-managment-system`, Volumes →
  ištrinti `dms-pgdata` ir `dms-caddy-data`, o projekto aplanke – `.env` ir `storage`.

### Dažnos problemos

| Klaida | Sprendimas |
|---|---|
| „running scripts is disabled on this system“ | Paleisk būtent taip: `powershell -ExecutionPolicy Bypass -File .\paleisti_auditorijoje.ps1`. |
| „Nerastas Python 3.13“ | Įdiek Python 3.13 su „Add python.exe to PATH“, uždaryk ir vėl atidaryk PowerShell. |
| „Docker Desktop nepasileido“ / „WSL“ klaidos | Atidaryk Docker Desktop ranka. Jei prašo atnaujinti WSL: PowerShell (administratorius) `wsl --update`, tada perkrauk kompiuterį. BIOS turi būti įjungta virtualizacija. |
| „Nepavyko paleisti Caddy“ (80 ar 443 prievadas užimtas) | Uždaryk programas, kurios užima šiuos prievadus (Skype, IIS, kitas web serveris, XAMPP), ir paleisk iš naujo. |
| „Nepavyko prisijungti prie DB“ po to, kai ištrynei `.env` | Senoji DB turi seną slaptažodį. Arba atkurk seną `.env`, arba ištrink DB: `docker rm -f document-managment-system`, `docker volume rm dms-pgdata` (dings visi duomenys) ir paleisk skriptą. |
| „Dirbtinio intelekto paslauga laikinai nepasiekiama“ | Pasiekta Gemini nemokamo rakto riba arba nėra interneto. Palauk ir bandyk dar kartą. Demonstracijai be DI paleisk be `-GeminiKey` ir `.env` faile nustatyk `USE_MOCK_AI=1`. |
| „Per daug bandymų“ prisijungiant | Iš vieno kompiuterio leidžiama 10 prisijungimų per minutę. Palauk minutę. |

---

# Techninė informacija (kūrėjui)

## Technologijos

| Sritis | Kas naudojama |
|---|---|
| Kalba | Python 3.13 |
| Duomenų bazė | PostgreSQL 16 su pgvector (Docker konteineris `document-managment-system`, prievadas 5433) |
| ORM | SQLAlchemy 2 |
| Teksto ištraukimas | pdfplumber (PDF), python-docx (DOCX) |
| Slaptažodžiai | bcrypt; 5 nesėkmingi bandymai – paskyra užrakinama 15 min. |
| DI | Gemini API: `gemini-embedding-001` (1536 dim. vektoriai), `gemini-3.5-flash-lite` atsakymams |
| Žiniatinklis | Flask + Flask-WTF (CSRF) + Flask-Limiter, serveris waitress |
| HTTPS | Caddy (Docker), vietinis sertifikatas |
| Testai | pytest, Locust (apkrova), OWASP ZAP (saugumas) |

## Įdiegimas rankiniu būdu (Windows, PowerShell, projekto šakniniame aplanke)

Tą patį automatiškai daro `paleisti_auditorijoje.ps1` (žr. aukščiau).

1. Įdiekite Python 3.13 ir Docker Desktop.
2. Sukurkite virtualią aplinką ir įdiekite paketus:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Nukopijuokite `.env.example` į `.env` ir įrašykite reikšmes (slaptažodį, Gemini API raktą iš Google AI Studio,
   ilgą atsitiktinę `FLASK_SECRET_KEY`). `.env` niekada nekeliamas į git.
4. Paleiskite duomenų bazę (pirmą kartą konteineris sukuriamas):
   ```powershell
   docker run -d --name document-managment-system -e POSTGRES_PASSWORD=<slaptažodis> -e POSTGRES_DB=docs_db `
     -p 127.0.0.1:5433:5432 -v dms-pgdata:/var/lib/postgresql/data pgvector/pgvector:pg16
   ```
   Vėliau užtenka `docker start document-managment-system`.
5. Sukurkite lenteles: `python -m init_db` (komanda `python -m init_db --reset` IŠTRINA visas lenteles – tik kūrimo metu).
   Kartu sukuriami KD padaliniai (Bendras, Personalo, Finansų ir kt.) ir dokumentų kategorijos (Nekategorizuota,
   Instrukcijos, Sutartys, Ataskaitos, Techniniai aprašymai); paleidus dar kartą pridedami tik trūkstami.
6. Testiniai vartotojai (QA forma E): `python -m scripts.make_test_users` (`--with-management` – dar ir
   `vadovas@test.lt` / `Vadovas1234!` su role „Valdymas“ ataskaitoms).
7. Testiniai failai F1–F4 (QA forma E): `python -m scripts.make_test_files` – atsiras aplanke `samples/test_files`.

## Paleidimas su HTTPS

```powershell
docker run -d --name dms-caddy -p 80:80 -p 443:443 `
  -v "${PWD}\Caddyfile:/etc/caddy/Caddyfile:ro" -v dms-caddy-data:/data caddy:2.10.2
$env:BEHIND_PROXY="1"; python -m run_web
```

Atidarykite <https://localhost>. `http://` automatiškai nukreipiamas į `https://`. Sertifikatą išduoda Caddy
vietinė sertifikavimo įstaiga, todėl naršyklė pirmą kartą perspės; demonstracijai galima pasitikėti Caddy šakniniu
sertifikatu (`docker cp dms-caddy:/data/caddy/pki/authorities/local/root.crt .` ir įdiegti „Trusted Root“).
Vėliau užtenka `docker start dms-caddy`.

Be HTTPS (tik kūrimui): `python -m run_web` ir <http://127.0.0.1:8000>.

## Viešas adresas testuotojui (Cloudflare Tunnel)

Kad kitas žmogus galėtų testuoti per internetą, nieko nediegdamas (instrukcija jam – `TESTUOTOJUI.docx`):

```powershell
docker start document-managment-system
$env:BEHIND_PROXY="1"; python -m run_web                                  # 1 langas
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:8000   # 2 langas
```

Antrame lange atsiras adresas `https://<atsitiktiniai-žodžiai>.trycloudflare.com` – jį nusiųskite testuotojui.
Adresas keičiasi kiekvieną kartą paleidus tunelį ir veikia tik kol kompiuteris įjungtas ir abu langai atidaryti.
Cloudflare pats nukreipia `http://` į `https://` ir perduoda tikrą lankytojo IP (prisijungimų riba veikia).
Baigus testuoti, uždarykite tunelio langą (Ctrl+C) – tada sistema iš interneto nebepasiekiama.

## Vartotojo vadovas

- **Kalba ir tema**: viršutinėje juostoje „LT | EN“ keičia sąsajos kalbą (numatyta – lietuvių), „Šviesi | Tamsi | Auto“ –
  spalvas („Auto“ – pagal kompiuterio nustatymus). Pasirinkimas įsimenamas naršyklėje. DI atsakymo kalba nuo to
  nepriklauso: atsakoma klausimo kalba (FR-03).
- **Prisijungimas**: el. paštas ir slaptažodis. Po 5 neteisingų bandymų paskyra užrakinama 15 minučių
  (tada atmetamas ir teisingas slaptažodis). Iš vieno IP leidžiama ne daugiau kaip 10 bandymų per minutę.
- **Mano dokumentai**: įkelkite PDF arba DOCX (iki 20 MB, iki 1000 dokumentų), pasirinkite kategoriją ir, jei reikia,
  dokumento datą (KD 5.2; padalinys ir autorius priskiriami pagal paskyrą). Kategoriją ir datą galima pakeisti
  dokumento peržiūroje. Būsena „Paruoštas“ reiškia, kad
  dokumente jau galima ieškoti; „Klaida“ – failo nepavyko perskaityti (pvz., nuskenuotas PDF be teksto, slaptažodžiu
  apsaugotas PDF). Dokumentą galima peržiūrėti, atsisiųsti, pervadinti ir ištrinti. Ištrynus pašalinamas failas,
  jo ištraukos ir visi klausimai bei atsakymai, kuriuose jis buvo cituojamas.
- **Apibendrinimai**: savo parengtą santraukos failą galima įkelti (FR-05), arba skiltyje „Sukurti apibendrinimą (PDF)“
  pažymėti iki 10 dokumentų – DI juos apibendrina lietuvių arba anglų kalba ir sistema išsaugo PDF failą skyriuje
  „Apibendrinimai“ (QA A3). PDF galima atsisiųsti, jame galima ieškoti kaip ir kituose dokumentuose. PDF šriftas:
  Windows Arial, kitur DejaVu Sans; kitą galima nurodyti `.env` (`DMS_FONT`, `DMS_FONT_BOLD`).
- **Klausimai**: (nebūtina) atrinkite dokumentus pagal kategoriją, pažymėkite dokumentus, įrašykite klausimą ir spauskite „Klausti“. Atsakymas pateikiamas klausimo
  kalba, su šaltiniais. DOCX neturi fiksuotų puslapių, todėl jų puslapis rodomas apytiksliai („≈ p.“, ~3000 simbolių).
  „Paieškos panašumas“ rodo, kiek rasta ištrauka panaši į klausimą – tai nėra tikimybė, kad atsakymas teisingas.
  Jei atsakymo dokumentuose nėra, sistema taip ir atsako.
- **Istorija**: paskutiniai 50 jūsų klausimų su atsakymais ir šaltiniais (iš užklausų žurnalo).
- **Ataskaitos** (rolės „Administratorius“ ir „Valdymas“, KD 5.6): pasirinktam laikotarpiui – klausimų skaičius,
  kiek atsakyta su šaltiniu ir kiek „informacijos nėra“, dažniausiai naudojami dokumentai, pasiskirstymas pagal
  kategorijas, padalinius ir dienas; administratorius dar mato įkėlimus ir aktyviausius vartotojus. Klausimų tekstai
  nerodomi. „Atsisiųsti CSV“ – ta pati ataskaita Excel formatu.

## Administratoriaus vadovas

- Administratorius (rolė `admin`) mato meniu punktą „Admin panelė“ (`/admin`): visus vartotojus, jų rolę, ar paskyra
  aktyvi ar užrakinta, ir kiek dokumentų turi; paspaudus skaičių – to vartotojo dokumentų sąrašą (be turinio).
  Kitiems vartotojams `/admin` grąžina 403 „Prieiga draudžiama“.
- **Vartotojai** (KD 5.5): „+ Naujas vartotojas“ – el. paštas, vardas, pavardė, padalinys, rolė ir laikinas
  slaptažodis. „Redaguoti“ – pakeisti duomenis, padalinį, rolę („Vartotojas“, „Administratorius“, „Valdymas“),
  išjungti paskyrą (išjungtas vartotojas iš karto atjungiamas), atblokuoti po 5 nesėkmingų bandymų, nustatyti naują
  slaptažodį. Savo paskyros išjungti ar atimti sau administratoriaus teisių negalima.
- **Kategorijos ir padaliniai**: pridėti, pervadinti, ištrinti. Kategorijos ar padalinio, kuris naudojamas, ištrinti
  negalima; pirmoji kategorija („Nekategorizuota“) – numatytoji.
- Atsarginė kopija prieš demonstraciją: `python -m scripts.backup_db` (failas `storage/backups/`); kartu nukopijuokite
  `storage/uploads/`. Atkūrimas aprašytas `scripts/backup_db.py`.
- Gemini modelių pavadinimai laikomi `.env` (`GEMINI_MODEL`, `EMBEDDING_MODEL`), nes Google senus modelius išjungia.
  `EMBEDDING_MODEL` ar `EMBEDDING_DIM` keisti tik kartu su `init_db --reset` ir visų dokumentų įkėlimu iš naujo.
- Prieš demonstraciją: `pip install --upgrade -r requirements.txt` ir `pip-audit`.

## Testavimas

| Komanda | Kas tikrinama |
|---|---|
| `python -m pytest` | 88 testai: apdorojimas, RAG, slaptažodžiai ir blokavimas, įkėlimo patikros, žiniatinklis (TS-01, TS-04, TS-05 dalys, CSRF, XSS, 403, kito vartotojo dokumentai), metaduomenys, PDF apibendrinimas, istorija, vartotojų, kategorijų ir padalinių valdymas, ataskaitos. Žiniatinklio testams reikia veikiančios DB, kitiems – ne |
| `python -m scripts.smoke_test` | visa grandinė su tikra DB ir DI imitacija |
| `python -m scripts.qa_acceptance` | QA scenarijų TS-01–TS-07 repeticija per veikiančią HTTPS svetainę su tikru Gemini; kiekvienas žingsnis lyginamas su „Laukiamas rezultatas“ (reikia `storage/caddy_root.crt`, žr. skripto aprašą) |
| `python -m scripts.make_test_files` | QA formos E testiniai failai F1–F4 į `samples/test_files/` (išgalvota įmonė, privačių duomenų nėra) ir `F4_klausimai.csv` |
| `python -m scripts.gold_set --f4` | TS-06 A / FR-02: 10 F4 dokumentų, po vieną klausimą; tikrina atsakymą, dokumentą, puslapį ir ≤ 30 s (reikia ≥ 9/10) |
| `python -m scripts.gold_set` | 10 klausimų su žinomais atsakymais per tikrą Gemini (TS-02, TS-03, TS-06 A dalis, NFR-02 ≤ 30 s) |
| `locust -f scripts/locustfile.py ...` | TS-06: 100 vartotojų; komanda faile. Serveris paleidžiamas su `USE_MOCK_AI=1` |
| `python -m scripts.fill_documents <el. paštas> 999` | TS-07: 1000 dokumentų ribai patikrinti (`--remove` – pašalina) |
| `python -m scripts.print_schema_sql` | PostgreSQL DDL iš modelių (KD 2 priedas) |
| `python -m scripts.benchmark_retrieval` | paieškos greitis, kai vartotojas turi 1000 dokumentų (~85 000 vektorių) |
| OWASP ZAP | `docker run --rm --network container:dms-caddy -v "${PWD}\storage\zap:/zap/wrk:rw" -t zaproxy/zap-stable:2.16.1 zap-baseline.py -t https://localhost/login -r zap_baseline.html` |

Rezultatai 2026-11-20: pytest 88/88; QA repeticija TS-01–TS-07 – visi ATITIKO (tikras Gemini).
Rezultatai 2026-11-17: pytest 69/69; smoke test – viskas praėjo; gold set 10/10 (lėčiausias atsakymas 11,1 s);
Locust 100 vartotojų, 6024 užklausos, 0 klaidų (su DI imitacija); paieška per 85 000 vektorių ~0,5 s;
ZAP baseline – 0 FAIL, likę įspėjimai informaciniai.

## Privatumas

Įkeltų dokumentų ištraukos siunčiamos Google Gemini API. Nemokamoje versijoje Google gali naudoti turinį savo
produktams tobulinti (žr. <https://ai.google.dev/gemini-api/terms>), todėl kol nenuspręsta dėl mokamos versijos
(plano sprendimas D5), įkelkite tik neprivačius testinius dokumentus. Ištrynus dokumentą, sistema pašalina visus jo
duomenis, bet negali atšaukti to, kas jau išsiųsta Gemini.
