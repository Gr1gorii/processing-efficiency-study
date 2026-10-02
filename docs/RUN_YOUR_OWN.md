# Run your own experiment

This repository measures three explicit implementations of a synthetic integer workload. It does not load arbitrary CSV files or automatically choose a processing engine. Keep the published data and results as the original experiment; collect a new campaign in a separate directory.

## Create a clean run directory

From the repository root, use a new destination name. These commands copy code, tests and protocol files, without copying measurements, generated data or the old frozen configuration.

```sh
set -eu
run_dir="../processing-efficiency-my-run"
mkdir "$run_dir"
mkdir "$run_dir/src" "$run_dir/docs"
cp src/dataset.py src/backends.py src/worker.py \
  src/collect.py src/analyze.py "$run_dir/src/"
cp -R tests "$run_dir/"
cp docs/METHODOLOGY.md docs/IMPLEMENTATION_ADDENDUM.md "$run_dir/docs/"
cp config.proposed.json requirements.txt "$run_dir/"
cd "$run_dir"
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The original environment was macOS with Python 3.12.14. The code uses POSIX facilities (`resource` and `os.getloadavg`), so native Windows is unsupported. Linux is not validated by the archived experiment. The worker treats macOS `ru_maxrss` as bytes and Linux values as KiB; other operating systems need verification. PNG rendering requires either Poppler's `pdftoppm` or macOS `sips`, independently of the Python requirements.

## Pilot, review, then freeze

Before collection, record your machine, hypotheses and intended changes in a new note under `docs/`. Keep the copied protocol as the historical reference. Edit `config.proposed.json` before running if needed. Use positive, unique sizes and a positive dimension count. Five main repeats are recommended; the analyzer requires at least three.

The following pilot commands match the supplied proposal:

```sh
python src/dataset.py --sizes 10000 50000 \
  --seed 20261001 --dimension-rows 5000
python src/collect.py --phase pilot --design config.proposed.json
```

Dataset CLI values must match the configuration's `data_seed`, `dimension_rows` and pilot sizes. Keep the default `data/` output: the collector always reads that project directory. Inspect `results/pilot/status.json` and `raw.csv`. Continue only when `complete` and `all_valid` are true and `stop_reason` is null. Review worker wall times and RSS before choosing feasible main sizes. Record that decision; do not change the design to pursue a preferred performance result.

Freeze a **new** configuration after reviewing the pilot. This example retains the supplied proposal; reduce `proposed_main_sizes` or `proposed_main_repeats` first if necessary:

```sh
python - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

pilot = json.loads(Path("results/pilot/status.json").read_text())
assert pilot["complete"] and pilot["all_valid"]
assert pilot["stop_reason"] is None
config = json.loads(Path("config.proposed.json").read_text())
config["status"] = "frozen_after_pilot"
config["main_sizes"] = config["proposed_main_sizes"]
config["main_repeats"] = config["proposed_main_repeats"]
config["frozen_utc"] = datetime.now(timezone.utc).isoformat()
with Path("config.main.json").open("x") as stream:
    json.dump(config, stream, indent=2)
PY
```

Generate only the missing sizes. For the unchanged proposal, 50,000 rows already exist from the pilot:

```sh
python src/dataset.py --sizes 250000 1000000 \
  --seed 20261001 --dimension-rows 5000
python src/collect.py --phase main --design config.main.json
python src/analyze.py --input results/main/raw.csv \
  --output results/analysis --charts charts \
  --machine-label "Your verified CPU model and installed RAM"
```

Replace the last label with verified hardware information, and adjust generation arguments to your frozen design. Keep all raw files, manifests, configuration and metadata together. Keep `status.json` and `schedule.json` beside `raw.csv` so their checks run. The analyzer overwrites its own outputs. Inspect both figures after rendering. The analyzer rejects incomplete or invalid campaigns.

## Budgets and practical changes

The collector stores one campaign clock when the pilot starts. The hardcoded 1,200-second deadline includes pilot collection, your review, data generation between phases, pauses and main collection. The separate default 900-second budget counts cumulative child-worker wall time. Finish both phases in one session, on the same machine and boot. Do not reset `results/campaign.json` to bypass a limit; preserve partial results and start a fresh directory if needed.

Set `max_cumulative_worker_seconds`, `per_worker_timeout_seconds` and `max_worker_peak_rss_bytes` conservatively before the pilot. The RSS threshold is checked after each worker finishes, not enforced as a live allocation cap. macOS swapout increases stop collection when `vm_stat` telemetry is available; Linux has no equivalent swapout check in this implementation. No temperature control or energy measurement is implemented.

To change a filter threshold, update all three implementations in `src/backends.py`, the independent oracle in `src/dataset.py`, and hand-calculated tests in `tests/test_correctness.py`. Regenerate inputs and expected digests in another clean run directory. Preserve identical sorted output contracts, integer sums and unique dimension keys. Adding an operation also requires updating the collector schedule, worker choices/output width, oracle generation and analyzer validation/plots.

The configuration lists `backends`, `operations`, `modes` and `threads` are descriptive: current code fixes these settings. Editing those lists alone does not change execution. Numerical-library thread limits are fixed at 1; SQLite `PRAGMA threads=1` permits one auxiliary thread. Compare results as observations from your machine, without universal speed or environmental claims.

The original report and audit scripts are specific to the archived experiment, including its sizes and narrative. They are intentionally omitted from this clean run directory; adapt them before using them for a changed study.
