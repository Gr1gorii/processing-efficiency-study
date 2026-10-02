"""Check saved measurements, provenance and summaries without new benchmarks."""

import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent.parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    groups = {}
    observation_count = 0
    for phase in ["pilot", "main"]:
        directory = ROOT / "results" / phase
        raw = json.loads((directory / "raw.json").read_text())
        jsonl = [json.loads(line) for line in (directory / "raw.jsonl").read_text().splitlines()]
        assert raw == jsonl, f"JSON and JSONL differ: {phase}"
        status = json.loads((directory / "status.json").read_text())
        assert status["complete"] and status["all_valid"] and status["stop_reason"] is None
        schedule = json.loads((directory / "schedule.json").read_text())
        assert len(raw) == len(schedule) == status["planned_trials"]
        assert len({row["order"] for row in raw}) == len(raw)  # Public data omit OS process IDs.
        with (directory / "raw.csv").open(newline="") as stream:
            csv_rows = list(csv.DictReader(stream))
        assert len(csv_rows) == len(raw)
        for row, csv_row, planned in zip(raw, csv_rows, schedule):
            assert all(row[key] == value for key, value in planned.items())
            assert row["valid"] and row["returncode"] == 0
            assert row["elapsed_seconds"] > 0 and row["peak_rss_bytes"] > 0
            assert float(csv_row["elapsed_seconds"]) == row["elapsed_seconds"]
            assert int(csv_row["peak_rss_bytes"]) == row["peak_rss_bytes"]
            manifest = json.loads((ROOT / "data" / f"synthetic_{row['rows']}.json").read_text())
            expected = manifest["expected"][row["operation"]]
            assert row["result_sha256"] == expected["sha256"]
            assert row["result_rows"] == expected["result_rows"]
            if phase == "main":
                key = (row["rows"], row["backend"], row["operation"], row["mode"])
                groups.setdefault(key, []).append(row)
        environment = json.loads((directory / "environment.json").read_text())
        for filename, digest in environment["code_sha256"].items():
            assert sha256(ROOT / "src" / filename) == digest, f"Measured code changed: {filename}"
        for filename, digest in environment.get("public_methodology_sha256", environment["methodology_sha256"]).items():
            assert sha256(ROOT / "docs" / filename) == digest
        for rows, digest in environment["data_sha256"].items():
            assert sha256(ROOT / "data" / f"synthetic_{rows}.npz") == digest
        observation_count += len(raw)
    checked_statistics = 0
    with (ROOT / "results/analysis/summary.csv").open(newline="") as stream:
        summaries = list(csv.DictReader(stream))
    assert len(summaries) == len(groups)
    for summary in summaries:
        key = (int(summary["rows"]), summary["backend"], summary["operation"], summary["mode"])
        observations = groups[key]
        assert int(summary["n"]) == len(observations)
        for metric in ["elapsed_seconds", "peak_rss_bytes"]:
            values = sorted(row[metric] for row in observations)
            quartiles = statistics.quantiles(values, n=4, method="inclusive")
            expected = dict(median=statistics.median(values), min=min(values), max=max(values),
                            q1=quartiles[0], q3=quartiles[2])
            for statistic, value in expected.items():
                assert abs(float(summary[f"{metric}_{statistic}"]) - value) <= max(1e-12, abs(value) * 1e-12)
                checked_statistics += 1
    campaign = json.loads((ROOT / "results/campaign.json").read_text())
    assert campaign["worker_wall_seconds"] < campaign["max_worker_wall_seconds"]
    for readme in ["README.md", "README.it.md"]:
        text = (ROOT / readme).read_text()
        assert not any(dash in text for dash in ["\u2013", "\u2014"])
        assert "AI-assisted" not in text
    for filename in ["README.md", "README.it.md", "docs/report_ru.md"]:
        lines = [line for line in (ROOT / filename).read_text().splitlines()
                 if line.startswith("|")][2:]
        expected_rows = []
        for mode in ["cold", "warm"]:
            for operation in ["filter", "group", "join"]:
                numbers = []
                for backend in ["python", "pandas", "sqlite"]:
                    value = statistics.median(r["elapsed_seconds"] for r in groups[1000000, backend, operation, mode])
                    numbers.append(f"{value * 1000:.2f}")
                expected_rows.append(numbers)
        assert len(lines) == len(expected_rows)
        for line, expected in zip(lines, expected_rows):
            cells = [cell.strip().replace(",", ".") for cell in line.split("|")[1:-1]]
            assert cells[-3:] == expected, f"Narrative table differs: {filename}: {line}"
    result = {"passed": True, "measured_results_checked": observation_count,
              "summary_cells_checked": len(groups), "summary_statistics_checked": checked_statistics,
              "checks": ["JSON/JSONL equality", "CSV time/RSS equality", "complete schedule and unique trial order",
                         "exact result digests", "measured code/data and public protocol hashes",
                         "independent summary recalculation", "narrative table values", "worker budget", "README text constraints"]}
    (ROOT / "results/final-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
