# Synthetic data processing experiment

Status: preregistered preparation only. No pilot or measurement runs started.

## Research question
How do ordinary Python loops, pandas and SQLite compare in elapsed time and peak process memory when they produce identical results from the same synthetic data on one Mac?

This is an original, bounded experiment for a portfolio and a draft post. It is not a benchmark of client data, a universal ranking, or an environmental study.

## Methods and environment
Use already installed Python 3.12.14, NumPy 2.3.5, pandas 2.2.3, and the Python sqlite3 module. DuckDB is unavailable. The preinstalled runtime path is in environment.json. No dependencies have been installed. SQLite substitutes for DuckDB because it is already available and supports the required SQL operations.

Hardware: MacBook Air, Mac15,12, Apple M3, 8 CPU cores (4 performance and 4 efficiency), 16 GB RAM, verified using system_profiler. Preserve software versions, platform, code hash, configuration hash, timestamps and available load information with the final run.

Use a sequential runner. Set OMP_NUM_THREADS, OPENBLAS_NUM_THREADS, MKL_NUM_THREADS, VECLIB_MAXIMUM_THREADS, NUMEXPR_NUM_THREADS to 1 before importing libraries. SQLite PRAGMA threads=1. These settings constrain supported library pools; they do not establish CPU affinity or equal internal execution strategies. Leave other applications and system settings alone. Record load averages before and after each worker and available CPU count. macOS scheduling and external applications remain uncontrolled confounders.

## Source data and operations
Generate one canonical set of int64 arrays per size with numpy.random.Generator(PCG64(seed)). Store compact NPZ files and SHA-256 hashes. All backends read the same source files. Do not generate data inside a timed region.

Fact schema: id, customer_id, category_id, amount_cents, status. IDs are unique and increasing. customer_id samples a fixed unique customer dimension with 5,000 rows. category_id has 64 possible values, status has 4 values, amount_cents is an integer in [-1000, 10000]. Customer schema: customer_id, segment_id, with 8 segments. No nulls or strings in the main workload. This intentionally narrow integer schema avoids float summation differences and makes exact correctness checks possible.

Operations, with identical output contracts:
1. Filter status == 1 and amount_cents >= 5000. Return (id, amount_cents) for every selected row, ordered by id. Materialize the complete selected result in every method.
2. Group all fact rows by category_id. Return (category_id, count, sum_amount_cents), ordered by category_id.
3. Inner JOIN fact to the unique customer dimension, then group by segment_id. Return (segment_id, count, sum_amount_cents), ordered by segment_id. The main data have complete foreign keys, so this join preserves fact count.

Include creation of canonical Python tuples from each backend result and ordering in query timing. Exclude correctness hashing and comparison from elapsed query time. State that whole-process memory can still include these validation allocations.

## Hypotheses fixed before measurement
H1: pandas warm filtering and grouping will be faster than basic Python loops at larger sizes.
H2: SQL JOIN plus aggregation may have a different time/memory tradeoff than pandas merge. This is a comparison to test, not a directional performance claim.
H3: loading and preparing data will change cold rankings relative to warm rankings.
Report all three operations and both modes, including results that contradict these hypotheses.

## Cold and warm definitions
Cold means a fresh worker process. Time starts immediately before reading the canonical NPZ and includes source loading, conversion to the backend representation, SQLite table population where applicable, operation execution and complete result materialization. Imports and process startup are outside the timer. No indexes other than the customer primary key are created. Cold is process-cold; OS file cache is not flushed and must not be described as disk-cold.

Warm means another fresh worker process first loads and prepares its data and executes the selected operation once without timing. Then it times one execution of that same operation, including output materialization, with preparation excluded. Each measured repeat uses a fresh independent worker and one untimed prime. SQLite may reuse its statement cache; all implementations may benefit from priming. Record that the memory metric includes preparation and priming.

Peak memory is resource.getrusage(RUSAGE_SELF).ru_maxrss, normalized for macOS bytes, captured near worker completion. Label it peak whole-worker RSS in MiB, including imports, loaded source arrays, backend structures, priming and validation. It is not incremental query memory, not a continuously sampled RSS value, and not memory allocated by the algorithm alone. Keep memory comparisons separate from the timing boundaries.

## Pilot and fixed main design
Pilot sizes: 10,000 and 50,000 fact rows, one repeat per backend/operation/mode. Pilot validates timing, correctness, process isolation and approximate limits. Keep pilot data separate from main results.

Proposed main sizes: 50,000, 250,000 and 1,000,000 fact rows; five independent repeats for each backend/operation/mode. This gives 270 main measurements plus 36 pilot measurements. Generate the main schedule using a fixed RNG seed and shuffle backend, operation and mode jobs within each repeat/size block; randomize block order too. Persist the full actual schedule. Keep the data seed and schedule seed distinct.

After the pilot and before any main run, freeze the final sizes and repeats in a main-design JSON. If projected load exceeds the budget, reduce the largest size and then repeats, preserving at least three repeats and all backends/operations/modes. Explain any change in a dated pilot decision. Do not adapt the design because of interesting results or continue until a preferred result appears.

## Stopping condition and safeguards
Maximum 900 seconds of cumulative worker wall time, including imports, preparation and untimed priming, across pilot and main measurements. Enforce a total measurement-campaign deadline too, and per-worker timeout of 30 seconds. A worker exceeding 2 GiB peak RSS stops escalation of dataset size. Use pauses between blocks if needed, counted separately from workload time. No simultaneous workers. If the pilot predicts the cap cannot be met, shrink the design before main measurement.

Stop on any exact-equivalence failure. Stop or reduce size if memory pressure or swapping becomes apparent through safe available telemetry. Do not query privileged telemetry, invoke sudo, change power/security settings, flush system caches, kill other processes or download large datasets. Thermal state is not assumed measurable; record this limitation. Do not deliberately heat the machine to a target state.

Completion means the frozen bounded design finishes or a safeguard stops it; correctness checks pass; raw results, analysis and graphs are verified; requested documentation and archive are produced. No indefinite expansion.

## Correctness and analysis
Write independent small hand-calculated fixtures covering threshold boundaries, negative amounts, absent categories, an empty selection and an unmatched customer for inner-join semantics. Test dimension uniqueness and join conservation on generated main data. Compare every timed result with a canonical exact reference outside elapsed timing using sorted tuples and a SHA-256 digest. Do not rely solely on two methods agreeing if they share a bug.

Save raw CSV and JSON with phase, job order, seeds, size, backend, operation, mode, repeat, UTC timestamps, elapsed seconds, peak RSS, startup/load metadata, exact-result digest and validation status. Save errors and partial runs rather than silently deleting them.

Analyze main data only for headline comparisons. Export grouped summary CSV with n, median, minimum, maximum and quartiles for elapsed time and RSS. Plot medians and all individual observations or min-max ranges. These are observed spreads, not population confidence intervals. With only five repeats on one machine, avoid significance tests, universal speed claims and extrapolation. Compute speed ratios from explicit median baselines and keep cold and warm separate.

## Energy
powermetrics is installed but reports that it must be invoked as the superuser. No acceptable energy telemetry has been established. Energy, power and CO2 are excluded. Elapsed time and memory are not converted into energy or environmental benefit.
