"""One independent trial. The parent owns process limits and job ordering."""

import time
PROCESS_START = time.perf_counter()

import argparse
import datetime
import gc
import json
import os
from pathlib import Path
import resource
import sys

# Set by runner before launch too; setting here protects direct invocations.
THREAD_VARIABLES = ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"]
for name in THREAD_VARIABLES:
    os.environ[name] = "1"

import numpy as np
from backends import BACKENDS
from dataset import digest_result


def rss_bytes():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--backend", choices=BACKENDS, required=True)
    parser.add_argument("--operation", choices=["filter", "group", "join"], required=True)
    parser.add_argument("--mode", choices=["cold", "warm"], required=True)
    args = parser.parse_args()
    if args.backend == "pandas":
        import pandas  # Backend-specific import stays outside the cold timer.
    expected = json.loads(args.data.with_suffix(".json").read_text())["expected"][args.operation]
    gc.collect()
    import_and_startup_seconds = time.perf_counter() - PROCESS_START
    baseline_peak = rss_bytes()
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cpu_before = time.process_time()
    begin = time.perf_counter_ns()
    load_start = begin
    with np.load(args.data, allow_pickle=False) as source:
        fact, customers = source["fact"], source["customers"]
    loaded = time.perf_counter_ns()
    backend = BACKENDS[args.backend](fact, customers)
    prepared = time.perf_counter_ns()
    prime_seconds = 0.0
    if args.mode == "warm":
        prime_start = time.perf_counter_ns()
        prime = backend.execute(args.operation)
        prime_seconds = (time.perf_counter_ns() - prime_start) / 1e9
        del prime
        gc.collect()
        cpu_before = time.process_time()
        begin = time.perf_counter_ns()
    result = backend.execute(args.operation)
    elapsed = (time.perf_counter_ns() - begin) / 1e9
    cpu_seconds = time.process_time() - cpu_before
    # Primary memory boundary is BEFORE digest validation.
    peak_query = rss_bytes()
    validation_start = time.perf_counter_ns()
    digest = digest_result(result, 2 if args.operation == "filter" else 3)
    valid = digest == expected["sha256"] and len(result) == expected["result_rows"]
    payload = {
        "backend": args.backend, "operation": args.operation, "mode": args.mode,
        "rows": len(fact), "elapsed_seconds": elapsed, "process_cpu_seconds": cpu_seconds,
        "peak_rss_bytes": peak_query, "baseline_peak_rss_bytes": baseline_peak,
        "end_peak_rss_bytes": rss_bytes(), "import_and_startup_seconds": import_and_startup_seconds,
        "source_load_seconds": (loaded - load_start) / 1e9,
        "prepare_seconds": (prepared - loaded) / 1e9, "prime_seconds": prime_seconds,
        "validation_seconds": (time.perf_counter_ns() - validation_start) / 1e9,
        "result_rows": len(result), "result_sha256": digest, "valid": valid,
        "started_utc": started, "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "pid": os.getpid(), "thread_settings": {k: os.environ[k] for k in THREAD_VARIABLES},
    }
    backend.close()
    print(json.dumps(payload), flush=True)
    if not valid:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
