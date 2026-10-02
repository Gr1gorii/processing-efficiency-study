#!/usr/bin/env python3
"""Validate real measurements, summarize them, and draw descriptive figures.

Run from the project root:
    .venv/bin/python src/analyze.py --input results/main/raw.csv \
        --output results/analysis --charts charts

No benchmark is executed here. PNG rendering uses pdftoppm if installed,
otherwise the built-in macOS sips utility. The PDF itself is vector graphics.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import shutil
import statistics
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.pdfgen import canvas


BACKENDS = ("python", "pandas", "sqlite")
OPERATIONS = ("filter", "group", "join")
MODES = ("cold", "warm")
GROUP_FIELDS = ("rows", "backend", "operation", "mode")
REQUIRED_FIELDS = (*GROUP_FIELDS, "repeat", "elapsed_seconds", "peak_rss_bytes", "valid")
BACKEND_LABELS = {"python": "Python loops", "pandas": "pandas", "sqlite": "SQLite"}
OPERATION_LABELS = {"filter": "Filter", "group": "Group and aggregate", "join": "JOIN and aggregate"}
PALETTE = {"python": "#2864B7", "pandas": "#C77816", "sqlite": "#19826A"}
INK = colors.HexColor("#18283D")
MUTED = colors.HexColor("#536476")
GRID = colors.HexColor("#DCE3EA")
MIB = 1024 * 1024


def integer(value: str, field: str, line: int, minimum: int = 0) -> int:
    """Do not silently accept decimals, empty values, or negative counts."""
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Line {line}: {field} must be an integer, got {value!r}") from exc
    if number < minimum:
        raise ValueError(f"Line {line}: {field} must be >= {minimum}")
    return number


def read_measurements(path: Path) -> tuple[list[dict], list[str]]:
    """Require one complete, valid, balanced main campaign before reporting."""
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames or []
        missing = set(REQUIRED_FIELDS) - set(fieldnames)
        if missing:
            raise ValueError(f"Missing required CSV columns: {sorted(missing)}")
        if len(fieldnames) != len(set(fieldnames)):
            raise ValueError("CSV has duplicate column names")
        records = []
        seen = set()
        for line, row in enumerate(reader, start=2):
            if None in row or any(row.get(field) is None for field in fieldnames):
                raise ValueError(f"Line {line}: inconsistent CSV column count")
            for field, allowed in (("backend", BACKENDS), ("operation", OPERATIONS), ("mode", MODES)):
                if row[field] not in allowed:
                    raise ValueError(f"Line {line}: unknown {field} {row[field]!r}")
            if row["valid"].strip().lower() not in {"true", "1"}:
                raise ValueError(f"Line {line}: correctness validation is not true")
            if "returncode" in row and row["returncode"] != "0":
                raise ValueError(f"Line {line}: measurement worker did not exit successfully")
            if "phase" in row and row["phase"] != "main":
                raise ValueError(f"Line {line}: only main measurements may enter headline analysis")
            row["rows"] = integer(row["rows"], "rows", line, minimum=1)
            row["repeat"] = integer(row["repeat"], "repeat", line)
            row["peak_rss_bytes"] = integer(row["peak_rss_bytes"], "peak_rss_bytes", line, minimum=1)
            try:
                row["elapsed_seconds"] = float(row["elapsed_seconds"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Line {line}: elapsed_seconds is not numeric") from exc
            if not math.isfinite(row["elapsed_seconds"]) or row["elapsed_seconds"] <= 0:
                raise ValueError(f"Line {line}: elapsed_seconds must be finite and positive")
            row["valid"] = True
            identity = tuple(row[field] for field in (*GROUP_FIELDS, "repeat"))
            if identity in seen:
                raise ValueError(f"Duplicate measurement: {identity}")
            seen.add(identity)
            records.append(row)
    if not records:
        raise ValueError("No measurements in the input CSV")

    sizes = sorted({row["rows"] for row in records})
    repeats = sorted({row["repeat"] for row in records})
    expected = set(itertools.product(sizes, BACKENDS, OPERATIONS, MODES, repeats))
    if seen != expected:
        missing = sorted(expected - seen)
        raise ValueError(f"Incomplete campaign: {len(missing)} missing cell/repeat combinations; examples: {missing[:6]}")
    if len(repeats) < 3:
        raise ValueError("At least three independent repeats per cell are required for main analysis")
    status_path = path.with_name("status.json")
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("complete") is not True or status.get("all_valid") is not True or status.get("stop_reason") is not None:
            raise ValueError("Collector status does not confirm a complete successful campaign")
    schedule_path = path.with_name("schedule.json")
    if schedule_path.exists():
        schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
        scheduled_keys = [tuple(job[field] for field in (*GROUP_FIELDS, "repeat")) for job in schedule]
        if len(scheduled_keys) != len(set(scheduled_keys)) or set(scheduled_keys) != seen:
            raise ValueError("Measured cells do not exactly match the preserved collection schedule")
    if "result_sha256" in fieldnames:
        hashes = defaultdict(set)
        for row in records:
            digest = row["result_sha256"]
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ValueError("Malformed result_sha256 in a measurement")
            hashes[row["rows"], row["operation"]].add(digest)
        if any(len(digests) != 1 for digests in hashes.values()):
            raise ValueError("Result digests disagree across methods, modes or repeats")
    return records, fieldnames


def quantile(values: list[float | int], probability: float) -> float:
    """Linear interpolation, equivalent to NumPy's default quantile method."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(records: list[dict]) -> tuple[list[dict], dict[tuple, list[dict]]]:
    grouped = defaultdict(list)
    for row in records:
        grouped[tuple(row[field] for field in GROUP_FIELDS)].append(row)
    summary = []
    for key in sorted(grouped):
        rows = grouped[key]
        result = dict(zip(GROUP_FIELDS, key))
        result["n"] = len(rows)
        for metric in ("elapsed_seconds", "peak_rss_bytes"):
            values = [row[metric] for row in rows]
            result.update({
                f"{metric}_median": statistics.median(values),
                f"{metric}_min": min(values),
                f"{metric}_max": max(values),
                f"{metric}_q1": quantile(values, 0.25),
                f"{metric}_q3": quantile(values, 0.75),
            })
        summary.append(result)
    return summary, grouped


def median_ratios(summary: list[dict]) -> list[dict]:
    """Pair matching experimental cells; these are ratios of medians."""
    baseline = {
        (row["rows"], row["operation"], row["mode"]): row
        for row in summary if row["backend"] == "python"
    }
    ratios = []
    for row in summary:
        reference = baseline[row["rows"], row["operation"], row["mode"]]
        ratios.append({
            **{field: row[field] for field in GROUP_FIELDS},
            "baseline_backend": "python",
            "n_backend": row["n"],
            "n_baseline": reference["n"],
            "backend_median_seconds": row["elapsed_seconds_median"],
            "python_median_seconds": reference["elapsed_seconds_median"],
            "time_speedup_python_over_backend": reference["elapsed_seconds_median"] / row["elapsed_seconds_median"],
            "backend_median_peak_rss_bytes": row["peak_rss_bytes_median"],
            "python_median_peak_rss_bytes": reference["peak_rss_bytes_median"],
            "memory_ratio_backend_over_python": row["peak_rss_bytes_median"] / reference["peak_rss_bytes_median"],
        })
    return ratios


def write_csv(path: Path, records: list[dict], fieldnames: list[str] | None = None) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames or list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def text(pdf: canvas.Canvas, x: float, y: float, value: str, size: float = 10,
         color=INK, bold: bool = False, align: str = "left") -> None:
    pdf.setFillColor(color)
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    methods = {"left": pdf.drawString, "center": pdf.drawCentredString, "right": pdf.drawRightString}
    methods[align](x, y, value)


def marker(pdf: canvas.Canvas, x: float, y: float, backend: str, radius: float,
           color, median: bool = False) -> None:
    pdf.setFillColor(color)
    pdf.setStrokeColor(colors.white if median else color)
    pdf.setLineWidth(0.9 if median else 0.5)
    if backend == "python":
        pdf.circle(x, y, radius, fill=1, stroke=1)
    elif backend == "pandas":
        pdf.rect(x - radius, y - radius, 2 * radius, 2 * radius, fill=1, stroke=1)
    else:
        shape = pdf.beginPath()
        shape.moveTo(x, y + radius * 1.2)
        shape.lineTo(x - radius * 1.1, y - radius * 0.85)
        shape.lineTo(x + radius * 1.1, y - radius * 0.85)
        shape.close()
        pdf.drawPath(shape, fill=1, stroke=1)


def compact_rows(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:g}M"
    if value >= 1_000:
        return f"{value / 1_000:g}k"
    return str(value)


def tick_label(value: float) -> str:
    if value >= 1000:
        return f"{value:,.0f}"
    return f"{value:g}"


def log_axis(values: list[float]) -> tuple[float, float, list[float]]:
    low = math.floor(math.log10(min(values)) * 2) / 2
    high = math.ceil(math.log10(max(values)) * 2) / 2
    if high <= low:
        high = low + 1
    # Leave visible breathing room at both boundaries, retaining round ticks.
    low -= 0.12
    high += 0.12
    ticks = []
    for exponent in range(math.floor(low), math.ceil(high) + 1):
        for multiplier in (1, 2, 5):
            tick = multiplier * 10 ** exponent
            if low <= math.log10(tick) <= high:
                ticks.append(tick)
    if len(ticks) > 9:
        ticks = [value for value in ticks if abs(math.log10(value) - round(math.log10(value))) < 1e-8]
    return 10 ** low, 10 ** high, ticks


def linear_axis(values: list[float]) -> tuple[float, float, list[float]]:
    rough_step = max(values) * 1.12 / 5
    magnitude = 10 ** math.floor(math.log10(rough_step))
    step = next(value * magnitude for value in (1, 2, 2.5, 5, 10) if value * magnitude >= rough_step)
    high = math.ceil(max(values) * 1.10 / step) * step
    return 0.0, high, [step * index for index in range(round(high / step) + 1)]


def draw_figure(path: Path, grouped: dict, metric: str, observation_count: int, machine_label: str) -> None:
    """Six panels. Points are measured observations; bars are observed ranges."""
    is_time = metric == "elapsed_seconds"
    width, height = 1200, 900
    pdf = canvas.Canvas(str(path), pagesize=(width, height), pageCompression=1)
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setTitle("Synthetic processing experiment: " + ("elapsed time" if is_time else "peak process memory"))
    pdf.setAuthor("")
    sizes = sorted({key[0] for key in grouped})
    repeat_counts = sorted({len(rows) for rows in grouped.values()})
    n_text = str(repeat_counts[0]) if len(repeat_counts) == 1 else f"{min(repeat_counts)}-{max(repeat_counts)}"

    text(pdf, 54, 857, "Elapsed time" if is_time else "Peak whole-worker memory", 26, bold=True)
    text(pdf, 54, 832, f"Synthetic integer workload | One machine | {machine_label}", 12, MUTED)
    text(pdf, 54, 812, f"{n_text} independent repeats per cell | {observation_count} measured runs | Same source data and exact result checks", 11, MUTED)
    for index, backend in enumerate(BACKENDS):
        xpos = 65 + index * 153
        marker(pdf, xpos, 786, backend, 5, colors.HexColor(PALETTE[backend]), median=True)
        text(pdf, xpos + 13, 782, BACKEND_LABELS[backend], 11)
    text(pdf, 550, 782, "Small marks: individual runs   Large marks: median   Bars: observed min-max", 10, MUTED)

    panel_width = 290
    panel_height = 210
    panel_lefts = (75, 465, 855)
    panel_bottoms = (485, 165)
    all_rows = [row for rows in grouped.values() for row in rows]
    multiplier = 1000 if is_time else 1 / MIB
    memory_axis = linear_axis([row[metric] * multiplier for row in all_rows]) if not is_time else None

    for mode_index, mode in enumerate(MODES):
        row_values = [row[metric] * multiplier for row in all_rows if row["mode"] == mode]
        low, high, ticks = log_axis(row_values) if is_time else memory_axis
        def position(value: float) -> float:
            if is_time:
                return (math.log10(value) - math.log10(low)) / (math.log10(high) - math.log10(low))
            return value / high

        for operation_index, operation in enumerate(OPERATIONS):
            left = panel_lefts[operation_index]
            bottom = panel_bottoms[mode_index]
            mode_label = "process-cold" if mode == "cold" else "warm"
            text(pdf, left, bottom + panel_height + 43, f"{OPERATION_LABELS[operation]} | {mode_label}", 13, bold=True)
            text(pdf, left, bottom + panel_height + 23,
                 "Elapsed time (ms, log; different cold/warm limits)"
                 if is_time else "Peak RSS (MiB, zero baseline)", 10, MUTED)
            for value in ticks:
                ypos = bottom + position(value) * panel_height
                pdf.setStrokeColor(GRID)
                pdf.setLineWidth(0.6)
                pdf.line(left, ypos, left + panel_width, ypos)
                text(pdf, left - 8, ypos - 3, tick_label(value), 9, MUTED, align="right")
            pdf.setStrokeColor(MUTED)
            pdf.setLineWidth(0.7)
            pdf.line(left, bottom, left + panel_width, bottom)
            group_width = panel_width / len(sizes)
            for size_index, size in enumerate(sizes):
                group_center = left + (size_index + 0.5) * group_width
                text(pdf, group_center, bottom - 18, compact_rows(size), 10, MUTED, align="center")
                for backend_index, backend in enumerate(BACKENDS):
                    center = group_center + (backend_index - 1) * group_width * 0.27
                    summary_x = center + 8
                    rows = sorted(grouped[size, backend, operation, mode], key=lambda row: row["repeat"])
                    values = [row[metric] * multiplier for row in rows]
                    color = colors.HexColor(PALETTE[backend])
                    y_min = bottom + position(min(values)) * panel_height
                    y_max = bottom + position(max(values)) * panel_height
                    pdf.setStrokeColor(color)
                    pdf.setLineWidth(1.3)
                    pdf.line(summary_x, y_min, summary_x, y_max)
                    pdf.line(summary_x - 4, y_min, summary_x + 4, y_min)
                    pdf.line(summary_x - 4, y_max, summary_x + 4, y_max)
                    for repeat_index, value in enumerate(values):
                        # Deterministic horizontal separation only; y is measured.
                        jitter = (repeat_index - (len(values) - 1) / 2) * min(3.0, 15 / len(values))
                        marker(pdf, center - 4 + jitter, bottom + position(value) * panel_height,
                               backend, 1.25, color)
                    marker(pdf, summary_x, bottom + position(statistics.median(values)) * panel_height,
                           backend, 4.0, color, median=True)
            text(pdf, left + panel_width / 2, bottom - 36, "Dataset size (fact rows)", 10, MUTED, align="center")

    pdf.showPage()
    pdf.save()


def render_png(pdf_path: Path) -> Path:
    output = pdf_path.with_suffix(".png")
    if shutil.which("pdftoppm"):
        command = ["pdftoppm", "-png", "-singlefile", "-scale-to", "2400", str(pdf_path), str(output.with_suffix(""))]
    elif shutil.which("sips"):
        command = ["sips", "-s", "format", "png", str(pdf_path), "--out", str(output), "--resampleWidth", "2400"]
    else:
        raise RuntimeError("PNG renderer unavailable: install Poppler (pdftoppm) or run on macOS with sips; PDFs were preserved")
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if result.returncode or not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"PNG rendering failed: {result.stderr or result.stdout}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("results/main/raw.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/analysis"))
    parser.add_argument("--charts", type=Path, default=Path("charts"))
    parser.add_argument("--machine-label", default="See recorded environment.json",
                        help="Verified hardware caption for this campaign; never inferred from the current host")
    args = parser.parse_args()
    records, fieldnames = read_measurements(args.input)
    summary, grouped = summarize(records)
    ratios = median_ratios(summary)
    args.output.mkdir(parents=True, exist_ok=True)
    args.charts.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "summary.csv", summary)
    write_csv(args.output / "ratios.csv", ratios)
    write_csv(args.output / "chart_observations.csv", records, fieldnames)
    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(args.input),
        "source_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "observation_count": len(records),
        "cell_count": len(summary),
        "rows": sorted({row["rows"] for row in records}),
        "repeats": sorted({row["repeat"] for row in records}),
        "quantiles": "Linear interpolation between adjacent ordered values; equivalent to numpy.quantile(method='linear').",
        "spread": "Observed min-max, not confidence intervals. All individual observations are plotted.",
        "time_ratio": "Python median elapsed seconds divided by the matching backend median; values above 1 indicate faster than Python in that cell.",
        "memory_ratio": "Backend median peak whole-worker RSS divided by matching Python median; values below 1 indicate lower peak RSS in that cell.",
        "ratio_pairing": "Matching rows, operation and mode; ratios of medians, not medians of paired run-level ratios.",
        "cold": "Fresh worker; load, backend preparation, operation and materialized output timed. Imports and process launch excluded. OS cache not flushed.",
        "warm": "Fresh worker; one untimed prime, then operation and materialized output timed. Loading and preparation excluded.",
        "memory": "Peak whole-worker RSS in bytes through query completion, including imports, source data, setup and warm prime. Not incremental query memory.",
        "machine_label": args.machine_label,
        "scope": "Synthetic integer workload on one machine. No energy or CO2 conclusions.",
        "summary": summary,
    }
    (args.output / "summary.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    figure_paths = []
    for metric, filename in (("elapsed_seconds", "elapsed_time.pdf"), ("peak_rss_bytes", "peak_memory.pdf")):
        pdf_path = args.charts / filename
        draw_figure(pdf_path, grouped, metric, len(records), args.machine_label)
        png_path = render_png(pdf_path)
        figure_paths.extend((str(pdf_path), str(png_path)))
    print(json.dumps({"observations": len(records), "cells": len(summary), "summary": str(args.output / "summary.csv"), "figures": figure_paths}, indent=2))


if __name__ == "__main__":
    main()
