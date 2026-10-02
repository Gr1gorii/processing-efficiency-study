"""Create a concise Russian summary and append the two verified vector figures."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, default=Path("/System/Library/Fonts/Supplemental/Arial.ttf"))
    parser.add_argument("--font-bold", type=Path, default=Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"))
    args = parser.parse_args()
    pdfmetrics.registerFont(TTFont("Report", str(args.font)))
    pdfmetrics.registerFont(TTFont("ReportBold", str(args.font_bold)))
    raw = json.loads((ROOT / "results/main/raw.json").read_text())
    cells = defaultdict(list)
    for row in raw:
        cells[row["rows"], row["backend"], row["operation"], row["mode"]].append(row)

    def median(backend, operation, mode, metric="elapsed_seconds", rows=1000000):
        return statistics.median(r[metric] for r in cells[rows, backend, operation, mode])

    def number(value):
        return f"{value:.2f}".replace(".", ",")

    output = ROOT / "reports"
    output.mkdir(exist_ok=True)
    first_page = output / "summary_ru.pdf"
    body = ParagraphStyle("body", fontName="Report", fontSize=10.3, leading=14,
                          textColor=colors.HexColor("#243247"), spaceAfter=9)
    title = ParagraphStyle("title", parent=body, fontName="ReportBold", fontSize=21, leading=25, spaceAfter=12)
    heading = ParagraphStyle("heading", parent=body, fontName="ReportBold", fontSize=12, leading=16, spaceBefore=6)
    small = ParagraphStyle("small", parent=body, fontSize=8.4, leading=11)
    story = [Paragraph("Одинаковые данные,<br/>разные способы обработки", title)]
    story.append(Paragraph("Python • pandas • SQLite | Apple M3, 16 GB RAM | 1 октября 2026", small))
    story.append(Paragraph("Реальные замеры на детерминированных synthetic-данных. 36 пилотных и 270 основных прогонов: три размера, три операции, cold/warm и пять повторов. Все результаты точно совпали с эталоном; шесть тестов корректности прошли.", body))
    story.append(Paragraph("Медианы на миллионе строк, мс", heading))
    table_rows = [["Операция", "Режим", "Python", "pandas", "SQLite"]]
    for mode in ["cold", "warm"]:
        for operation, label in [("filter", "Фильтр"), ("group", "Группировка"), ("join", "JOIN + агрегация")]:
            table_rows.append([label, mode] + [number(median(b, operation, mode) * 1000)
                                               for b in ["python", "pandas", "sqlite"]])
    table = Table(table_rows, colWidths=[147, 62, 75, 75, 75], rowHeights=[23] * 7)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Report"), ("FONTNAME", (0, 0), (-1, 0), "ReportBold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F6")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#243247")),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#B6C2CE")),
        ("LINEBELOW", (0, 3), (-1, 3), 0.5, colors.HexColor("#CBD5DF")),
        ("LINEBELOW", (0, 6), (-1, 6), 0.5, colors.HexColor("#CBD5DF")),
    ]))
    story.extend([table, Spacer(1, 12)])
    ratios = [median("python", op, "warm") / median("pandas", op, "warm") for op in ["filter", "group", "join"]]
    story.append(Paragraph(f"На миллионе строк pandas быстрее Python по медиане warm-времени в {number(ratios[0])}, {number(ratios[1])} и {number(ratios[2])} раза для фильтра, группировки и JOIN соответственно.", body))
    story.append(Paragraph("На 50 тыс. строк warm-фильтр быстрее у Python: 1,13 против 1,35 мс. С загрузкой и подготовкой быстрее pandas: 3,42 против 9,94 мс. Граница таймера меняет порядок именно в этом случае.", body))
    story.append(Paragraph("Для warm-JOIN peak RSS у SQLite равен 128,91 MiB против 229,83 MiB у pandas, но время SQLite больше. Это различие между временем и памятью, а не единый рейтинг эффективности.", body))
    story.append(Paragraph("Границы измерения и ограничения", heading))
    story.append(Paragraph("Cold включает чтение, подготовку и полный ответ; импорт и запуск процесса исключены. Warm включает операцию и полный ответ после прогрева. Кеш ОС не очищался. Peak RSS охватывает весь процесс до проверки ответа, включая библиотеки, исходные данные и подготовку.", small))
    story.append(Paragraph("Одна машина, пять повторов, целочисленная схема без null и строк. Системный loadavg за минуту: 4,17-5,24; фон и температура не изолированы. SQLite threads=1 допускает один вспомогательный поток. На графиках все повторы и наблюдаемый минимум/максимум, не доверительные интервалы.", small))
    story.append(Paragraph("Работа процессов: 90,20 с; максимальный RSS: 282,08 MiB. Энергия не измерялась, выводов о CO2 нет. Источники в архиве: results/main/raw.csv, results/analysis/summary.csv; методика и воспроизводимый код включены. Следующие две страницы: все измеренные условия.", small))
    document = SimpleDocTemplate(str(first_page), pagesize=A4, rightMargin=30, leftMargin=30,
                                 topMargin=28, bottomMargin=26, title="Одинаковые данные, разные способы обработки", author="")
    def white_page(canvas, document):
        canvas.saveState()
        canvas.setFillColor(colors.white)
        canvas.rect(0, 0, *A4, fill=1, stroke=0)
        canvas.restoreState()

    document.build(story, onFirstPage=white_page, onLaterPages=white_page)
    assert len(PdfReader(first_page).pages) == 1, "Summary overflowed: fix layout before delivery"
    writer = PdfWriter()
    for path in [first_page, ROOT / "charts/elapsed_time.pdf", ROOT / "charts/peak_memory.pdf"]:
        writer.append(path)
    writer.add_metadata({"/Title": "Одинаковые данные, разные способы обработки", "/Author": ""})
    final_path = output / "synthetic-processing-report-ru.pdf"
    writer.write(final_path)
    first_page.unlink()
    print(f"Created {final_path}, {len(writer.pages)} pages")


if __name__ == "__main__":
    main()
