"""QA form E test files F1–F4 (fictional company, no private data – safe for the free Gemini tier).

    python -m scripts.make_test_files            # writes samples/test_files/
    python -m scripts.make_test_files --out DIR

F1 atostogu_tvarka.pdf (LT)   – TS-01, TS-02, TS-04, TS-06 B, TS-07
F2 travel_policy.docx (EN)    – TS-03, TS-04, TS-07
F3 santrauka_2026.pdf (LT)    – TS-01 step 4 (summary file)
F4 dok01.pdf … dok10.pdf (LT) – TS-06 A / FR-02: one fact each, 2 pages, the fact on a known page.
   F4_klausimai.csv lists the 10 questions, expected answers and pages; `python -m scripts.gold_set --f4` runs them.

The PDFs need a TrueType font with Lithuanian letters: Windows Arial by default, override with DMS_FONT=path.
"""
import argparse
import csv
import os
from pathlib import Path

from docx import Document as DocxDocument
from docx.shared import Pt
from fpdf import FPDF

COMPANY = "UAB „Testinė įmonė“ (išgalvota mokomajam projektui)"
FONT = os.getenv("DMS_FONT", r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = os.getenv("DMS_FONT_BOLD", r"C:\Windows\Fonts\arialbd.ttf")

F1_TEXT = [
    "1. Bendrosios nuostatos",
    "Ši tvarka nustato, kaip įmonės darbuotojai planuoja, prašo ir naudoja kasmetines atostogas. "
    "Tvarka taikoma visiems darbuotojams, dirbantiems pagal darbo sutartis.",
    "2. Kasmetinių atostogų trukmė",
    "Kasmetinės atostogos trunka 20 darbo dienų. Atostogos gali būti dalijamos į dalis, tačiau "
    "viena iš dalių turi būti ne trumpesnė kaip 10 darbo dienų.",
    "3. Prašymo pateikimas",
    "Prašymą reikia pateikti likus ne mažiau kaip 14 dienų iki atostogų pradžios. Prašymas teikiamas "
    "per vidinę personalo sistemą, jį tvirtina tiesioginis vadovas.",
    "4. Atostogų grafikas",
    "Padalinių vadovai kasmet sudaro atostogų grafiką ir su juo supažindina darbuotojus. "
    "Grafiką galima keisti abiejų šalių susitarimu.",
]

F2_TEXT = [
    ("Travel Expense Policy", True),
    ("1. Scope", True),
    ("This policy applies to all employees who travel on company business. It explains which costs "
     "the company reimburses and how to claim them.", False),
    ("2. Daily limit", True),
    ("Employees may claim travel expenses up to 100 EUR per day. The limit covers meals, local "
     "transport and other small costs; accommodation is booked by the office.", False),
    ("3. Receipts", True),
    ("Receipts must be submitted within 30 days after the trip. Claims without receipts are not "
     "reimbursed.", False),
    ("4. Approval", True),
    ("Every business trip must be approved by the employee's manager before booking.", False),
]

F3_TEXT = [
    "Vidaus tvarkų santrauka, 2026 m.",
    "Apibendrinimas: kasmetinės atostogos – 20 darbo dienų; kelionės išlaidos – iki 100 EUR per dieną.",
    "Atostogų prašymas teikiamas likus ne mažiau kaip 14 dienų iki atostogų pradžios, o kelionės "
    "čekiai pateikiami per 30 dienų po kelionės.",
    "Šią santrauką parengė darbuotojas savo reikmėms; oficialios yra tik pačios tvarkos.",
]

# (file, title, fact sentence, page the fact is on, question, expected words – any one must appear)
F4 = [
    ("dok01.pdf", "Darbo laiko tvarka",
     "Biuras dirba pirmadieniais–ketvirtadieniais nuo 8:00 iki 17:00, o penktadieniais nuo 8:00 iki 15:45.",
     1, "Koks yra biuro darbo laikas?", ["17:00", "17 val"]),
    ("dok02.pdf", "Nuotolinio darbo tvarka",
     "Darbuotojas gali dirbti nuotoliniu būdu ne daugiau kaip 2 dienas per savaitę.",
     2, "Kiek dienų per savaitę galima dirbti nuotoliniu būdu?", ["2 dien", "dvi dien"]),
    ("dok03.pdf", "Pertraukų tvarka",
     "Pietų pertrauka trunka 45 minutes ir būna nuo 12:00 iki 12:45.",
     1, "Kiek trunka pietų pertrauka?", ["45 min"]),
    ("dok04.pdf", "Kvalifikacijos kėlimo tvarka",
     "Kiekvienam darbuotojui per metus skiriama 5 mokymų dienos ir iki 600 EUR mokymų biudžetas.",
     2, "Koks yra metinis mokymų biudžetas vienam darbuotojui?", ["600"]),
    ("dok05.pdf", "Darbo priemonių tvarka",
     "Darbuotojo nešiojamasis kompiuteris keičiamas nauju kas 4 metus.",
     1, "Kas kiek laiko keičiamas darbuotojo nešiojamasis kompiuteris?", ["4 met", "ketver"]),
    ("dok06.pdf", "Informacijos saugos tvarka",
     "Slaptažodis turi būti ne trumpesnis kaip 12 simbolių ir keičiamas kas 90 dienų.",
     2, "Kas kiek dienų reikia keisti slaptažodį?", ["90"]),
    ("dok07.pdf", "IT pagalbos tvarka",
     "Dėl kompiuterio gedimo reikia skambinti IT pagalbos vidiniu telefono numeriu 555.",
     1, "Kokiu vidiniu numeriu kreiptis į IT pagalbą?", ["555"]),
    ("dok08.pdf", "Darbo užmokesčio tvarka",
     "Darbo užmokestis mokamas du kartus per mėnesį: 10 ir 25 mėnesio dieną.",
     1, "Kada mokamas darbo užmokestis?", ["25"]),
    ("dok09.pdf", "Priešgaisrinės saugos tvarka",
     "Kilus gaisrui, visi darbuotojai renkasi automobilių stovėjimo aikštelėje prie A korpuso.",
     2, "Kur renkasi darbuotojai kilus gaisrui?", ["A korpus"]),
    ("dok10.pdf", "Sveikatos draudimo tvarka",
     "Papildomą sveikatos draudimą darbdavys apmoka darbuotojui išdirbus 3 mėnesius.",
     2, "Po kiek laiko darbuotojui apmokamas sveikatos draudimas?", ["3 mėn", "trij"]),
]

FILLER = [
    "Ši tvarka parengta tam, kad visi darbuotojai vienodai suprastų taisykles ir jas taikytų kasdieniame darbe. "
    "Su tvarka darbuotojai supažindinami pasirašytinai, o jos laikymąsi prižiūri padalinių vadovai.",
    "Iškilus klausimams, darbuotojas pirmiausia kreipiasi į savo tiesioginį vadovą. Jei klausimo išspręsti "
    "nepavyksta, jis perduodamas personalo skyriui, kuris atsako raštu.",
    "Tvarka peržiūrima kartą per metus. Apie pakeitimus darbuotojai informuojami elektroniniu paštu ir "
    "vidiniame portale, o ankstesnės redakcijos saugomos archyve.",
    "Šios tvarkos pažeidimai nagrinėjami teisės aktų nustatyta tvarka. Prieš priimant sprendimą, darbuotojui "
    "suteikiama galimybė pateikti paaiškinimą.",
]


class _Pdf(FPDF):
    def header(self):
        self.set_font("body", size=8)
        self.cell(0, 6, COMPANY, align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("body", size=8)
        self.cell(0, 10, f"{self.page_no()} psl.", align="C")


def _pdf() -> _Pdf:
    pdf = _Pdf(format="A4")
    pdf.add_font("body", "", FONT)
    pdf.add_font("body", "B", FONT_BOLD)
    pdf.set_margins(25, 20, 20)
    return pdf


def _title(pdf: _Pdf, text: str) -> None:
    pdf.set_font("body", "B", 15)
    pdf.multi_cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def _para(pdf: _Pdf, text: str, bold: bool = False) -> None:
    pdf.set_font("body", "B" if bold else "", 12 if bold else 11)
    pdf.multi_cell(0, 6.5, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2.5)


def make_f1(out: Path) -> None:
    pdf = _pdf()
    pdf.add_page()
    _title(pdf, "Kasmetinių atostogų tvarka")
    for line in F1_TEXT:
        _para(pdf, line, bold=line[:2].rstrip(".").isdigit() and len(line) < 40)
    pdf.output(str(out / "atostogu_tvarka.pdf"))


def make_f2(out: Path) -> None:
    doc = DocxDocument()
    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = Pt(11)
    doc.add_paragraph(COMPANY).runs[0].font.size = Pt(8)
    for text, heading in F2_TEXT:
        if heading:
            doc.add_heading(text, level=1 if text[0].isalpha() else 2)
        else:
            doc.add_paragraph(text)
    doc.save(out / "travel_policy.docx")


def make_f3(out: Path) -> None:
    pdf = _pdf()
    pdf.add_page()
    _title(pdf, F3_TEXT[0])
    for line in F3_TEXT[1:]:
        _para(pdf, line)
    pdf.output(str(out / "santrauka_2026.pdf"))


def make_f4(out: Path) -> None:
    for number, (name, title, fact, fact_page, _question, _expected) in enumerate(F4):
        pdf = _pdf()
        for page in (1, 2):
            pdf.add_page()
            if page == 1:
                _title(pdf, title)
            # rotate the filler so neighbouring documents do not look identical
            paragraphs = [FILLER[(number + page + i) % len(FILLER)] for i in range(2)]
            if page == fact_page:
                paragraphs.insert(1, fact)
            for i, text in enumerate(paragraphs, start=1):
                _para(pdf, f"{page}.{i}. {text}")
        pdf.output(str(out / name))
    with open(out / "F4_klausimai.csv", "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["failas", "klausimas", "laukiamas atsakymas", "puslapis"])
        for name, _title_, fact, page, question, _expected in F4:
            writer.writerow([name, question, fact, page])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="samples/test_files")
    out = Path(parser.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    make_f1(out)
    make_f2(out)
    make_f3(out)
    make_f4(out)
    for path in sorted(out.iterdir()):
        print(f"{path}  {path.stat().st_size // 1024 or 1} KB")


if __name__ == "__main__":
    main()
