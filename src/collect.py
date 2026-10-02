"""Randomized, sequential trials with an append-only measurement ledger."""

import argparse
import csv
import datetime
import itertools
import json
import os
from pathlib import Path
import platform
import random
import re
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
THREAD_ENV = {key: "1" for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"]}
os.environ.update(THREAD_ENV)

from dataset import file_sha256


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def telemetry():
    """Read only aggregate system counters; do not inspect other applications."""
    result = {"load_average": list(os.getloadavg())}
    if sys.platform == "darwin":
        try:
            completed = subprocess.run(["vm_stat"], text=True, capture_output=True, timeout=3)
        except (subprocess.TimeoutExpired, OSError) as error:
            result["vm_stat_error"] = str(error)
            return result
        if completed.returncode == 0:
            values = dict(re.findall(r"^([^:\n]+):\s+(\d+)\.", completed.stdout, re.M))
            for key in ["Pages free", "Pages throttled", "Pageouts", "Swapouts"]:
                if key in values:
                    result[key] = int(values[key])
        else:
            result["vm_stat_error"] = completed.stderr.strip()
    return result


def make_schedule(sizes, repeats, seed):
    rng = random.Random(seed)
    blocks = list(itertools.product(sizes, range(1, repeats + 1)))
    rng.shuffle(blocks)
    jobs = []
    for block, (rows, repeat) in enumerate(blocks, 1):
        combinations = list(itertools.product(["python", "pandas", "sqlite"],
                                              ["filter", "group", "join"], ["cold", "warm"]))
        rng.shuffle(combinations)
        for backend, operation, mode in combinations:
            jobs.append(dict(order=len(jobs) + 1, block=block, rows=rows, repeat=repeat,
                             backend=backend, operation=operation, mode=mode))
    return jobs


def save_raw(records, directory):
    (directory / "raw.json").write_text(json.dumps(records, indent=2) + "\n")
    columns = list(dict.fromkeys(key for record in records for key in record))
    with (directory / "raw.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow({key: json.dumps(value) if isinstance(value, (dict, list)) else value
                             for key, value in record.items()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["pilot", "main"], required=True)
    parser.add_argument("--design", type=Path, default=ROOT / "config.proposed.json")
    args = parser.parse_args()
    config = json.loads(args.design.read_text())
    if args.phase == "pilot":
        sizes, repeats = config["pilot_sizes"], config["pilot_repeats"]
    else:
        if config.get("status") != "frozen_after_pilot":
            raise ValueError("Main collection requires a frozen design, not proposed sizes")
        sizes, repeats = config["main_sizes"], config["main_repeats"]
    output = ROOT / "results" / args.phase
    output.mkdir(parents=True, exist_ok=True)
    if (output / "raw.jsonl").exists():
        raise FileExistsError("Collection already exists. Preserve it; use a separate project copy for a rerun.")
    campaign_path = ROOT / "results" / "campaign.json"
    if campaign_path.exists():
        campaign = json.loads(campaign_path.read_text())
    else:
        campaign = {"started_utc": utc_now(), "start_monotonic": time.monotonic(),
                    "worker_wall_seconds": 0.0, "deadline_seconds": 1200,
                    "max_worker_wall_seconds": config["max_cumulative_worker_seconds"]}
    campaign_path.write_text(json.dumps(campaign, indent=2) + "\n")
    seed = config["schedule_seed"] + (1 if args.phase == "pilot" else 0)
    jobs = make_schedule(sizes, repeats, seed)
    (output / "schedule.json").write_text(json.dumps(jobs, indent=2) + "\n")
    hashes = {}
    for rows in sizes:
        data = ROOT / "data" / f"synthetic_{rows}.npz"
        manifest = json.loads(data.with_suffix(".json").read_text())
        assert manifest["rows"] == rows
        assert manifest["seed"] == config["data_seed"]
        assert manifest["dimension_rows"] == config["dimension_rows"]
        hashes[str(rows)] = file_sha256(data)
        assert hashes[str(rows)] == manifest["npz_sha256"]
    import numpy
    import pandas
    metadata = {
        "phase": args.phase, "captured_utc": utc_now(), "python": sys.version,
        "python_executable": sys.executable, "numpy": numpy.__version__,
        "pandas": pandas.__version__, "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "thread_environment": THREAD_ENV, "data_sha256": hashes,
        "design_sha256": file_sha256(args.design), "schedule_seed": seed,
        "methodology_sha256": {name: file_sha256(ROOT / "docs" / name)
                               for name in ["METHODOLOGY.md", "IMPLEMENTATION_ADDENDUM.md"]},
        "code_sha256": {p.name: file_sha256(p) for p in Path(__file__).parent.glob("*.py")
                        if p.name != "analyze.py"},
        "pragmas": {"threads": 1, "temp_store": "MEMORY", "database": ":memory:",
                    "customer_primary_key": True, "fact_indexes": []},
        "rss_boundary": "whole worker through timed query completion, before correctness digest",
        "baseline": telemetry(), "energy_measured": False,
    }
    (output / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
    records, stop_reason = [], None
    previous_block = None
    for job in jobs:
        if previous_block is not None and job["block"] != previous_block:
            time.sleep(1)  # Brief pause; never run workers concurrently.
        previous_block = job["block"]
        before = telemetry()
        if before.get("Swapouts", 0) > metadata["baseline"].get("Swapouts", 0):
            stop_reason = "system_swapouts_increased"
            break
        budget_remaining = campaign["max_worker_wall_seconds"] - campaign["worker_wall_seconds"]
        deadline_remaining = campaign["deadline_seconds"] - (time.monotonic() - campaign["start_monotonic"])
        timeout = min(config["per_worker_timeout_seconds"], budget_remaining, deadline_remaining)
        if timeout < 1:
            stop_reason = "campaign_time_limit"
            break
        started = time.perf_counter()
        command = [sys.executable, str(ROOT / "src" / "worker.py"),
                   "--data", str(ROOT / "data" / f"synthetic_{job['rows']}.npz"),
                   "--backend", job["backend"], "--operation", job["operation"], "--mode", job["mode"]]
        record = {**job, "phase": args.phase, "data_seed": config["data_seed"],
                  "schedule_seed": seed, "load_before": before["load_average"],
                  "telemetry_before": before, "valid": False}
        try:
            process = subprocess.run(command, capture_output=True, text=True,
                                     timeout=timeout, env={**os.environ, **THREAD_ENV})
            if process.stdout.strip():
                record.update(json.loads(process.stdout))
            record["returncode"] = process.returncode
            if process.stderr:
                record["stderr"] = process.stderr
            if process.returncode != 0:
                stop_reason = "worker_failed"
        except subprocess.TimeoutExpired as error:
            # subprocess.run terminates only this task's child worker.
            record["error"] = str(error)
            stop_reason = "worker_timeout"
        except (ValueError, OSError) as error:
            record["error"] = str(error)
            stop_reason = "worker_error"
        wall = time.perf_counter() - started
        campaign["worker_wall_seconds"] += wall
        record["worker_wall_seconds"] = wall
        record["telemetry_after"] = telemetry()
        record["load_after"] = record["telemetry_after"]["load_average"]
        records.append(record)
        with (output / "raw.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        campaign_path.write_text(json.dumps(campaign, indent=2) + "\n")
        if not record["valid"]:
            stop_reason = stop_reason or "correctness_failure"
        if record.get("peak_rss_bytes", 0) > config["max_worker_peak_rss_bytes"]:
            stop_reason = "peak_rss_limit"
        if record["telemetry_after"].get("Swapouts", 0) > metadata["baseline"].get("Swapouts", 0):
            stop_reason = "system_swapouts_increased"
        if job["order"] % 9 == 0 or stop_reason:
            print(f"{args.phase}: {len(records)}/{len(jobs)} trials; cumulative worker wall {campaign['worker_wall_seconds']:.1f}s; stop={stop_reason}", flush=True)
        if stop_reason:
            break
    save_raw(records, output)
    status = {"finished_utc": utc_now(), "planned_trials": len(jobs),
              "completed_trials": len(records), "all_valid": all(r["valid"] for r in records),
              "stop_reason": stop_reason, "complete": len(records) == len(jobs) and stop_reason is None,
              "cumulative_worker_seconds": campaign["worker_wall_seconds"],
              "campaign_elapsed_seconds": time.monotonic() - campaign["start_monotonic"]}
    (output / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps(status), flush=True)
    if not status["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
