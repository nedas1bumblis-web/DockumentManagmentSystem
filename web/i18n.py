"""Interface language: Lithuanian (default, the QA forms quote these texts) or English, chosen in the header.

Texts are written in Lithuanian in the code and templates and wrapped in _(): with English selected, _() looks the
Lithuanian text up in EN. A text missing from EN is shown in Lithuanian (tests/test_web.py checks that none is missing).
Placeholders use str.format: _("„{title}“ įkeltas ir apdorotas.", title=...).
AI answers are not translated: they follow the language of the question (FR-03).
"""
from flask import g, request

from app_config import MAX_DOCUMENTS_PER_USER, MAX_UPLOAD_BYTES
from security import LOCK_MINUTES, MAX_FAILED_ATTEMPTS
from services.qa import MAX_QUESTION_CHARS
from services.summary import MAX_SUMMARY_DOCUMENTS

LANGUAGES = {"lt": "Lietuvių", "en": "English"}
DEFAULT_LANGUAGE = "lt"
LANG_COOKIE = "lang"
MB = MAX_UPLOAD_BYTES // (1024 * 1024)

EN = {
    # layout
    "Žinių bazė": "Knowledge base",
    "Įmonės žinių bazė": "Company knowledge base",
    "Mano dokumentai": "My documents",
    "Klausimai": "Questions",
    "Admin panelė": "Admin panel",
    "Atsijungti": "Log out",
    "Spalvų tema": "Colour theme",
    "Šviesi": "Light",
    "Tamsi": "Dark",
    "Pagal sistemą": "Follow system",
    "Kalba": "Language",
    "Auto": "Auto",
    # login
    "Prisijungimas": "Sign in",
    "Klauskite apie savo dokumentus – atsakymai su šaltiniais.": "Ask about your documents – answers come with sources.",
    "El. paštas": "Email",
    "Slaptažodis": "Password",
    "Prisijungti": "Sign in",
    "Neteisingas slaptažodis arba el. paštas.": "Wrong password or email.",
    f"Paskyra užblokuota {LOCK_MINUTES} minučių po {MAX_FAILED_ATTEMPTS} nesėkmingų bandymų.":
        f"Account locked for {LOCK_MINUTES} minutes after {MAX_FAILED_ATTEMPTS} failed attempts.",
    "Paskyra išjungta. Kreipkitės į administratorių.": "Account disabled. Contact the administrator.",
    # documents
    "Įkelkite PDF ar DOCX failus ir užduokite klausimus apie jų turinį.":
        "Upload PDF or DOCX files and ask questions about their content.",
    "Įkelti dokumentą": "Upload a document",
    "Įkelti apibendrinimą": "Upload a summary",
    f"Failas (PDF arba DOCX, iki {MB} MB)": f"File (PDF or DOCX, up to {MB} MB)",
    "Apibendrinimo failas (PDF arba DOCX)": "Summary file (PDF or DOCX)",
    "Pavadinimas (nebūtina)": "Title (optional)",
    "Įkelti": "Upload",
    "Dokumentai": "Documents",
    "Apibendrinimai": "Summaries",
    "Dar neįkėlėte nė vieno dokumento.": "You have not uploaded any documents yet.",
    "Apibendrinimų nėra.": "No summaries.",
    "Pavadinimas": "Title",
    "Tipas": "Type",
    "Būsena": "Status",
    "Psl.": "Pages",
    "Įkelta": "Uploaded",
    "Veiksmai": "Actions",
    "Naujas pavadinimas": "New title",
    "Išsaugoti": "Save",
    "Ištrinti": "Delete",
    "Paruoštas": "Ready",
    "Apdorojamas": "Processing",
    "Klaida": "Error",
    "Pasirinkite failą.": "Choose a file.",
    "Apibendrinimas „{title}“ išsaugotas.": "Summary “{title}” saved.",
    "„{title}“ įkeltas ir apdorotas.": "“{title}” uploaded and processed.",
    "„{title}“ nepavyko apdoroti: {error}": "“{title}” could not be processed: {error}",
    "Pavadinimas pakeistas.": "Title changed.",
    "Dokumentas ir visi jo duomenys ištrinti.": "The document and all its data were deleted.",
    # upload and processing errors (services/storage.py, services/documents.py, processing/, services/ingest.py)
    "Palaikomi tik PDF ir DOCX failai.": "Only PDF and DOCX files are supported.",
    "Failo turinys neatitinka jo plėtinio.": "The file content does not match its extension.",
    "DOCX failas sugadintas.": "The DOCX file is damaged.",
    "Tai ne Word dokumentas.": "This is not a Word document.",
    "Išskleistas dokumentas per didelis.": "The unpacked document is too large.",
    "Failas tuščias.": "The file is empty.",
    f"Failas didesnis nei {MB} MB.": f"The file is larger than {MB} MB.",
    f"Galima saugoti ne daugiau kaip {MAX_DOCUMENTS_PER_USER} dokumentų.":
        f"You can store at most {MAX_DOCUMENTS_PER_USER} documents.",
    "PDF failas apsaugotas slaptažodžiu.": "The PDF file is password-protected.",
    "PDF failas sugadintas arba neperskaitomas.": "The PDF file is damaged or unreadable.",
    "DOCX failas sugadintas arba neperskaitomas.": "The DOCX file is damaged or unreadable.",
    "Faile nerasta teksto (nuskenuotam dokumentui reikia teksto atpažinimo).":
        "No text found in the file (a scanned document needs text recognition).",
    "Apdoroti nepavyko, bandykite vėliau.": "Processing failed, try again later.",
    # preview
    "psl.": "pages",
    "įkelta": "uploaded",
    "Atsisiųsti originalą": "Download the original",
    "Dokumentas dar apdorojamas.": "The document is still being processed.",
    "Ištrauktas tekstas": "Extracted text",
    "Ištrauka": "Excerpt",
    "p.": "p.",
    "≈ p.": "≈ p.",
    # ask
    "Atsakymas parengiamas tik pagal pažymėtus jūsų dokumentus ir nurodo šaltinį.":
        "Answers are based only on the documents you select and cite their source.",
    "Pirma įkelkite bent vieną dokumentą skiltyje": "First upload at least one document in",
    "Dokumentai, kuriuose ieškoti": "Documents to search",
    "Klausimas (lietuvių arba anglų kalba)": "Question (Lithuanian or English)",
    "Pvz.: Kiek dienų trunka kasmetinės atostogos?": "E.g.: How many days of annual leave are there?",
    "Klausti": "Ask",
    "Atsakymas": "Answer",
    "Šaltiniai": "Sources",
    "Paieškos panašumas:": "Search similarity:",
    "(tai ištraukos panašumas į klausimą, o ne tikimybė, kad atsakymas teisingas).":
        "(how similar the excerpt is to the question, not the probability that the answer is right).",
    "Pasirinkite bent vieną dokumentą.": "Select at least one document.",
    "Klausimas tuščias.": "The question is empty.",
    f"Klausimas ilgesnis nei {MAX_QUESTION_CHARS} simbolių.":
        f"The question is longer than {MAX_QUESTION_CHARS} characters.",
    "Dirbtinio intelekto paslauga laikinai nepasiekiama. Bandykite dar kartą.":
        "The AI service is temporarily unavailable. Please try again.",
    # admin
    "Vartotojai, jų būsena ir dokumentų skaičius.": "Users, their status and number of documents.",
    "Vartotojai": "Users",
    "Administratoriai": "Administrators",
    "Užblokuoti dabar": "Locked now",
    "Išjungti": "Disabled",
    "Dokumentai iš viso": "Documents in total",
    "Paieška": "Search",
    "El. paštas, vardas arba pavardė": "Email, first or last name",
    "Rolė": "Role",
    "Visos": "All",
    "Visi": "All",
    "Vartotojas": "User",
    "Administratorius": "Administrator",
    "Valdymas": "Management",
    "Užblokuoti": "Locked",
    "Turi dokumentų": "Has documents",
    "Rikiuoti": "Sort by",
    "Registracijos tvarka": "Registration order",
    "Pavardė": "Last name",
    "Daugiausia dokumentų": "Most documents",
    "Rodyti": "Show",
    "Išvalyti": "Clear",
    "Rodoma {first}–{last} iš {total}": "Showing {first}–{last} of {total}",
    "(filtruota)": "(filtered)",
    "Nieko nerasta": "Nothing found",
    "Puslapiai": "Pages",
    "← Ankstesnis": "← Previous",
    "Kitas →": "Next →",
    "Vardas, pavardė": "Name",
    "Išjungta": "Disabled",
    "Užblokuota iki {time}": "Locked until {time}",
    "Aktyvi": "Active",
    "Pagal šiuos filtrus vartotojų nėra.": "No users match these filters.",
    "Rodyti visus": "Show all",
    "← Admin panelė": "← Admin panel",
    "Dokumentai: {email}": "Documents: {email}",
    "dokumentų sąrašas (be turinio)": "list of documents (without content)",
    "{count} dok.": "{count} doc.",
    "Rūšis": "Kind",
    "Apibendrinimas": "Summary",
    "Dokumentas": "Document",
    "Šis vartotojas dokumentų neturi.": "This user has no documents.",
    # metadata (KD 5.2) and search by category (KD 5.3.2)
    "Kategorija": "Category",
    "Dokumento data": "Document date",
    "Dokumento data (nebūtina)": "Document date (optional)",
    "Padalinys": "Department",
    "Autorius": "Author",
    "Pakeitimai išsaugoti.": "Changes saved.",
    "Tokios kategorijos nėra.": "There is no such category.",
    "Neteisinga dokumento data.": "Invalid document date.",
    "Dokumento data negali būti ateityje.": "The document date cannot be in the future.",
    "Rodyti tik kategorijos dokumentus": "Show only documents of the category",
    "Šioje kategorijoje paruoštų dokumentų nėra.": "There are no ready documents in this category.",
    # generated summary (QA A3)
    "Sukurti apibendrinimą (PDF)": "Create a summary (PDF)",
    "Dirbtinis intelektas apibendrins pažymėtus dokumentus (iki {n}) ir išsaugos PDF failą skyriuje „Apibendrinimai“.":
        "AI will summarise the selected documents (up to {n}) and save a PDF file under “Summaries”.",
    "Dokumentai, kuriuos apibendrinti": "Documents to summarise",
    "Apibendrinimo kalba": "Summary language",
    "Lietuvių": "Lithuanian",
    "Anglų": "English",
    "Sukurti PDF": "Create PDF",
    "Apibendrinimas „{title}“ sukurtas.": "Summary “{title}” created.",
    f"Apibendrinti galima ne daugiau kaip {MAX_SUMMARY_DOCUMENTS} dokumentų vienu metu.":
        f"You can summarise at most {MAX_SUMMARY_DOCUMENTS} documents at once.",
    "Nerastas šriftas PDF failui (nurodykite DMS_FONT faile .env).":
        "No font for the PDF file was found (set DMS_FONT in .env).",
    # history
    "Istorija": "History",
    "Klausimų istorija": "Question history",
    "Paskutiniai jūsų klausimai ir atsakymai iš užklausų žurnalo (naujausi viršuje).":
        "Your latest questions and answers from the query log (newest first).",
    "Dar neuždavėte nė vieno klausimo.": "You have not asked any questions yet.",
    "Šaltinių nėra.": "No sources.",
    # admin: users (KD 5.5)
    "+ Naujas vartotojas": "+ New user",
    "Naujas vartotojas": "New user",
    "Redaguoti": "Edit",
    "Vartotojo duomenys, padalinys ir prieigos teisės (rolė).": "User details, department and access rights (role).",
    "Duomenys ir teisės": "Details and rights",
    "Vardas": "First name",
    "Laikinas slaptažodis (bent 8 simboliai)": "Temporary password (at least 8 characters)",
    "Sukurti": "Create",
    "Paskyra aktyvi": "Account active",
    "Paskyra užblokuota po {n} nesėkmingų bandymų.": "The account is locked after {n} failed attempts.",
    "Atblokuoti": "Unlock",
    "Paskyra neužblokuota.": "The account is not locked.",
    "Naujas slaptažodis (bent 8 simboliai)": "New password (at least 8 characters)",
    "Pakeisti slaptažodį": "Change password",
    "Sukurta": "Created",
    "Vartotojas {email} sukurtas.": "User {email} created.",
    "Paskyra atblokuota.": "Account unlocked.",
    "Slaptažodis pakeistas.": "Password changed.",
    "Neteisingas el. pašto adresas.": "Invalid email address.",
    "Vartotojas su tokiu el. paštu jau yra.": "A user with this email already exists.",
    "Pasirinkite padalinį.": "Choose a department.",
    "Neteisinga rolė.": "Invalid role.",
    "Negalite atimti administratoriaus teisių ar išjungti savo paskyros.":
        "You cannot remove your own administrator rights or disable your own account.",
    "Slaptažodis turi būti ne trumpesnis nei 8 simboliai.": "The password must be at least 8 characters long.",
    "Slaptažodis per ilgas (daugiausia 72 baitai).": "The password is too long (at most 72 bytes).",
    # admin: categories and departments
    "Kategorijos ir padaliniai": "Categories and departments",
    "Dokumentų metaduomenys: kategorija ir padalinys. Naudojamų įrašų ištrinti negalima.":
        "Document metadata: category and department. Entries in use cannot be deleted.",
    "Kategorijos": "Categories",
    "Aprašymas": "Description",
    "numatytoji": "default",
    "Nauja kategorija": "New category",
    "Pridėti": "Add",
    "Padaliniai": "Departments",
    "Pavadinimas, kodas, aprašymas": "Name, code, description",
    "Naujas padalinys": "New department",
    "Kodas": "Code",
    "Kategorija išsaugota.": "Category saved.",
    "Kategorija ištrinta.": "Category deleted.",
    "Padalinys išsaugotas.": "Department saved.",
    "Padalinys ištrintas.": "Department deleted.",
    "Kategorija tokiu pavadinimu jau yra.": "A category with this name already exists.",
    "Numatytosios kategorijos ištrinti negalima.": "The default category cannot be deleted.",
    "Kategorijos, kuriai priskirta dokumentų, ištrinti negalima.": "A category that has documents cannot be deleted.",
    "Padalinys tokiu kodu jau yra.": "A department with this code already exists.",
    "Padalinio, kuriame yra vartotojų ar dokumentų, ištrinti negalima.":
        "A department that has users or documents cannot be deleted.",
    # reports (KD 5.6)
    "Ataskaitos": "Reports",
    "Sistemos naudojimo ataskaita": "System usage report",
    "Žinių bazės naudojimo ataskaita": "Knowledge base usage report",
    "Pagal užklausų žurnalą. Klausimų tekstai nerodomi.": "Built from the query log. Question texts are not shown.",
    "Atsisiųsti CSV": "Download CSV",
    "Nuo": "From",
    "Iki": "To",
    "Klausimų": "Questions",
    "Atsakyta su šaltiniu": "Answered with a source",
    "Informacijos nerasta": "Information not found",
    "Klaususių vartotojų": "Users who asked",
    "Įkelta dokumentų": "Documents uploaded",
    "Nepavyko apdoroti": "Failed to process",
    "Vartotojų iš viso": "Users in total",
    "Dokumentų iš viso": "Documents in total",
    "Dažniausiai naudojami dokumentai": "Most used documents",
    "Atsakymų": "Answers",
    "Per šį laikotarpį dokumentai necituoti.": "No documents were cited in this period.",
    "Pagal kategorijas": "By category",
    "Pagal padalinius": "By department",
    "Duomenų nėra.": "No data.",
    "Klausimai pagal dienas": "Questions per day",
    "Diena": "Day",
    "Per šį laikotarpį klausimų nebuvo.": "There were no questions in this period.",
    "Aktyviausi vartotojai": "Most active users",
    "Įkėlė dokumentų": "Documents uploaded",
    "Per šį laikotarpį aktyvių vartotojų nebuvo.": "There were no active users in this period.",
    # errors
    "← Grįžti į pradžią": "← Back to start",
    "Prieiga draudžiama": "Access denied",
    "Neturite teisės matyti šio puslapio.": "You are not allowed to see this page.",
    "Nerasta": "Not found",
    "Puslapis arba dokumentas nerastas.": "The page or document was not found.",
    "Failas per didelis": "File too large",
    f"Didžiausias leidžiamas dydis: {MB} MB.": f"The maximum size is {MB} MB.",
    "Per daug bandymų": "Too many attempts",
    "Palaukite minutę ir bandykite dar kartą.": "Wait a minute and try again.",
    "Sesija pasibaigė": "Session expired",
    "Atnaujinkite puslapį ir bandykite dar kartą.": "Reload the page and try again.",
    "Įvyko klaida": "Something went wrong",
    "Bandykite dar kartą vėliau.": "Please try again later.",
}


def current_language() -> str:
    if "lang" not in g:
        chosen = request.cookies.get(LANG_COOKIE, DEFAULT_LANGUAGE)
        g.lang = chosen if chosen in LANGUAGES else DEFAULT_LANGUAGE
    return g.lang


def gettext(text: str, **values) -> str:
    """Lithuanian text -> the text in the chosen language, with {placeholders} filled in."""
    if text and current_language() == "en":
        text = EN.get(text, text)
    return text.format(**values) if values else text
