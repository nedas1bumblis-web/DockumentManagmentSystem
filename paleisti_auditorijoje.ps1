<#
  Paleidžia sistemą auditorijoje: duomenų bazę, HTTPS (Caddy) ir svetainę, kad kiti tame pačiame tinkle
  galėtų ją atidaryti naršyklėje adresu https://<šio kompiuterio IP>.

  Paleidimas (PowerShell, projekto aplanke; geriausia „Run as administrator“, kad būtų atidaryta ugniasienė):
      powershell -ExecutionPolicy Bypass -File .\paleisti_auditorijoje.ps1

  Parametrai (nebūtini):
      -Ip 192.168.1.23        jei automatiškai parinktas IP adresas netinka
      -GeminiKey "AIza..."    įrašo Gemini API raktą į .env ir įjungia tikrą DI (kitaip – DI imitacija)

  Pirmą kartą skriptas viską atsisiunčia (reikia interneto, ~10–20 min.), vėliau užtrunka ~1 min.
  Sustabdyti: Ctrl+C šiame lange, tada  docker stop dms-caddy document-managment-system
#>
param(
    [string]$Ip = "",
    [string]$GeminiKey = "",
    # for testing the script next to an existing installation; leave the defaults in the classroom
    [string]$DbContainer = "document-managment-system",
    [string]$DbVolume = "dms-pgdata",
    [int]$DbPort = 5433
)

$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot
$CaddyContainer = "dms-caddy"
$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Stop-WithError([string]$Text) {
    Write-Host ""
    Write-Host "KLAIDA: $Text" -ForegroundColor Red
    Write-Host "Žr. README.md skyrių „Dažnos problemos“." -ForegroundColor Yellow
    exit 1
}

function New-Secret([int]$Bytes) {
    $buffer = New-Object byte[] $Bytes
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return ([Convert]::ToBase64String($buffer) -replace '[+/=]', '')
}

function Get-EnvValue([string]$Name) {
    foreach ($line in Get-Content -LiteralPath ".env" -Encoding UTF8) {
        if ($line -match "^\s*$Name\s*=(.*)$") { return $Matches[1].Trim() }
    }
    return ""
}

function Set-EnvValue([string]$Name, [string]$Value) {
    $lines = @(Get-Content -LiteralPath ".env" -Encoding UTF8)
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$Name\s*=") { $lines[$i] = "$Name=$Value"; $found = $true }
    }
    if (-not $found) { $lines += "$Name=$Value" }
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot ".env"), (($lines -join "`r`n") + "`r`n"), (New-Object Text.UTF8Encoding $false))
}

# ---------- 1. Python ----------
Write-Step "1/7 Python 3.13 ir paketai"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    $made = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.13 -m venv .venv
        $made = ($LASTEXITCODE -eq 0)
    }
    if (-not $made) {
        $version = (& python --version) 2>&1
        if ("$version" -notmatch "Python 3\.13") {
            Stop-WithError "Nerastas Python 3.13 (rasta: $version). Įdiekite Python 3.13 iš python.org ir pažymėkite „Add python.exe to PATH“."
        }
        & python -m venv .venv
        if ($LASTEXITCODE -ne 0) { Stop-WithError "Nepavyko sukurti .venv aplanko." }
    }
}
& $VenvPython -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Stop-WithError "Nepavyko įdiegti paketų (ar yra interneto ryšys?)." }
Write-Host "Paketai įdiegti."

# ---------- 2. .env ----------
Write-Step "2/7 Nustatymai (.env)"
if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Set-EnvValue "PGPASSWORD" (New-Secret 18)
    Set-EnvValue "FLASK_SECRET_KEY" (New-Secret 48)
    Set-EnvValue "GEMINI_API_KEY" ""
    Set-EnvValue "USE_MOCK_AI" "1"
    Set-EnvValue "PGPORT" "$DbPort"
    Write-Host "Sukurtas .env su atsitiktiniais slaptažodžiais. DI – imitacija (be Gemini rakto)."
}
if ($GeminiKey) {
    Set-EnvValue "GEMINI_API_KEY" $GeminiKey
    Set-EnvValue "USE_MOCK_AI" "0"
    Write-Host "Gemini raktas įrašytas, įjungtas tikras DI."
}
$PgPassword = Get-EnvValue "PGPASSWORD"
if (-not $PgPassword -or $PgPassword -like "put-*") { Stop-WithError "Faile .env nėra PGPASSWORD reikšmės." }
if ((Get-EnvValue "USE_MOCK_AI") -eq "1") {
    Write-Host "DĖMESIO: DI veikia imitacijos režimu (atsakymas = tinkamiausia ištrauka). Tikram DI: -GeminiKey ""raktas""." -ForegroundColor Yellow
}

# ---------- 3. Docker ----------
Write-Step "3/7 Docker Desktop"
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $desktop)) { Stop-WithError "Docker Desktop neįdiegtas." }
    Write-Host "Paleidžiamas Docker Desktop (iki 3 min.)..."
    Start-Process -FilePath $desktop
    for ($i = 0; $i -lt 36; $i++) {
        Start-Sleep -Seconds 5
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { break }
    }
    if ($LASTEXITCODE -ne 0) { Stop-WithError "Docker Desktop nepasileido. Atidarykite jį ranka, palaukite „Engine running“ ir paleiskite skriptą iš naujo." }
}
Write-Host "Docker veikia."

# ---------- 4. Database ----------
Write-Step "4/7 Duomenų bazė (PostgreSQL + pgvector)"
$existing = docker ps -a --filter "name=^$DbContainer$" --format "{{.Names}}"
if ($existing -ne $DbContainer) {
    # 127.0.0.1 only: the database must not be reachable from the classroom network
    docker run -d --name $DbContainer -e "POSTGRES_PASSWORD=$PgPassword" -e POSTGRES_DB=docs_db `
        -p "127.0.0.1:$((Get-EnvValue 'PGPORT')):5432" -v "${DbVolume}:/var/lib/postgresql/data" pgvector/pgvector:pg16 | Out-Null
} else {
    docker start $DbContainer | Out-Null
}
if ($LASTEXITCODE -ne 0) { Stop-WithError "Nepavyko paleisti duomenų bazės konteinerio." }
for ($i = 0; $i -lt 60; $i++) {
    docker exec $DbContainer pg_isready -h 127.0.0.1 -U postgres -d docs_db *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
}
if ($LASTEXITCODE -ne 0) { Stop-WithError "Duomenų bazė neatsako." }
& $VenvPython -m init_db
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "Nepavyko prisijungti prie DB. Jei .env buvo sukurtas iš naujo, o DB – sena, žr. „Dažnos problemos“."
}

# ---------- 5. Test data ----------
Write-Step "5/7 Testiniai vartotojai ir failai"
& $VenvPython -m scripts.make_test_users
if (-not (Test-Path -LiteralPath "samples\test_files\dok10.pdf")) { & $VenvPython -m scripts.make_test_files }

# ---------- 6. HTTPS for the network ----------
Write-Step "6/7 HTTPS (Caddy) šio kompiuterio tinklo adresui"
if (-not $Ip) {
    $config = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } |
              Select-Object -First 1
    if ($config) { $Ip = @($config.IPv4Address)[0].IPAddress }
}
if (-not $Ip) { Stop-WithError "Neradau tinklo IP adreso. Prisijunkite prie Wi-Fi arba nurodykite: -Ip 192.168.x.x" }
docker rm -f $CaddyContainer *> $null
docker run -d --name $CaddyContainer -p 80:80 -p 443:443 -e "DMS_HOST=$Ip" -e "DMS_SITES=localhost, $Ip" `
    -v "$PSScriptRoot\Caddyfile:/etc/caddy/Caddyfile:ro" -v dms-caddy-data:/data caddy:2.10.2 | Out-Null
if ($LASTEXITCODE -ne 0) { Stop-WithError "Nepavyko paleisti Caddy. Gal 80 ar 443 prievadą užima kita programa (Skype, IIS)?" }
New-Item -ItemType Directory -Force -Path "storage" | Out-Null
for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Seconds 1
    docker cp "${CaddyContainer}:/data/caddy/pki/authorities/local/root.crt" "storage\caddy_root.crt" *> $null
    if ($LASTEXITCODE -eq 0) { break }
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    if (-not (Get-NetFirewallRule -DisplayName "DMS HTTPS (80, 443)" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "DMS HTTPS (80, 443)" -Direction Inbound -Protocol TCP -LocalPort 80, 443 `
            -Action Allow -Profile Any | Out-Null
    }
    Write-Host "Ugniasienė: 80 ir 443 prievadai atidaryti."
} else {
    Write-Host "DĖMESIO: skriptas paleistas ne administratoriaus teisėmis – ugniasienės taisyklė nesukurta." -ForegroundColor Yellow
    Write-Host "Jei kiti negali atidaryti adreso, paleiskite PowerShell „Run as administrator“ ir skriptą dar kartą." -ForegroundColor Yellow
}

# ---------- 7. Web app ----------
Write-Step "7/7 Svetainė"
Write-Host ""
Write-Host "=================================================================" -ForegroundColor Green
Write-Host "  Kursiokams duokite adresą:   https://$Ip" -ForegroundColor Green
Write-Host "  Šiame kompiuteryje:          https://localhost" -ForegroundColor Green
Write-Host ""
Write-Host "  Naršyklė perspės dėl sertifikato: „Išplėstiniai“ -> „Tęsti“."
Write-Host "  Paskyros: admin@test.lt / Admin1234!"
Write-Host "            vartotojas1@test.lt, vartotojas2@test.lt, user001@test.lt ... user100@test.lt / Test1234!"
Write-Host ""
Write-Host "  NEUŽDARYKITE šio lango. Sustabdyti – Ctrl+C." -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Green
$env:BEHIND_PROXY = "1"
& $VenvPython -m run_web
