# Public data and provenance

This repository contains a public copy of a completed synthetic experiment. No benchmark was repeated while preparing the repository. The original local files remain unchanged.

## Removed metadata

- `python_executable` was removed from the preparation, pilot and main environment JSON files because it contained an absolute personal filesystem path.
- The ephemeral operating-system `pid` field was removed from pilot/main JSON, JSONL and CSV, and from the chart observation CSV. No replacement process IDs were invented.
- `start_monotonic` was removed from `results/campaign.json`. It described the original system clock origin, not measured elapsed time.
- Local environments, caches, delivery receipts, intermediate renders, internal status notes and the original unsanitized ZIP are excluded.

Every other field of every raw observation is unchanged, including elapsed time, CPU time, peak RSS, preparation time, priming time, result counts, result digests, order, seeds, timestamps and aggregate load/swap counters. All 306 observations remain present. The four collection modules and deterministic NPZ inputs are byte-identical to the originals. The scientific protocol is unchanged; its final administrative delivery section was omitted from the public Markdown.

## What each checksum means

Collection-time `code_sha256`, `methodology_sha256` and `data_sha256` preserve the hashes recorded for code, the original protocol and inputs. `public_methodology_sha256` identifies the protocol files as published after removal of the administrative delivery section. `design_sha256` and `config.main.json.pilot_raw_sha256` retain historical provenance; the latter hashes the private original pilot JSON before PID removal, not the public JSON.

The public analysis was recalculated from the sanitized CSV. Its `summary.json.source_sha256` hashes that public CSV. `PUBLIC-MANIFEST.json` records the actual published file hashes. A hash mismatch between an original raw file and its public copy is expected because metadata was removed; it does not indicate changed measurements.

The public audit verifies a complete schedule and unique trial order. It does not infer unique OS processes from that order. Unique worker PIDs were verified before removal; the preserved aggregate audit records 270 distinct main workers. Exact result equivalence, preserved code/input hashes and numerical summaries remain independently checkable.

## Reports and reuse

The original Russian PDF and editable DOCX reports are retained as separate documents. Their measured results remain valid. The historical report links to an earlier local ZIP; use GitHub Code > Download ZIP for this public version instead. Any process-ID statement in them describes verification of the original private logs before metadata removal.

The private original protocol remains preserved locally. The public audit verifies the published protocol against `public_methodology_sha256`; it does not claim that the shortened Markdown has the original collection-time hash.
