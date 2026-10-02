# Pilot decision

Frozen UTC: 2026-10-01T18:16:23.614335+00:00

All 36 pilot trials passed exact result checks. Total parent-observed worker time was 5.518 seconds; largest observed peak RSS was 73.5 MiB. There were no reported swapout increases or safeguards triggered.

Retain the proposed main design: 50,000, 250,000 and 1,000,000 rows; five fresh-worker repeats for each of three backends, three operations and two modes, totaling 270 measurements. No outcome-driven changes.

A deliberately conservative feasibility projection scales the entire 50,000-row worker wall time linearly with row count, including fixed import overhead. Across the planned design this gives 386.7 seconds, below the remaining 900-second cumulative budget. Baseline RSS plus linearly scaled RSS above that baseline projects at most 304.2 MiB at one million rows. These are pilot planning estimates, not results, and do not appear in performance charts. Actual limits remain enforced.

Implementation review clarified SQLite's documented PRAGMA threads=1 semantics: this allows at most one auxiliary query thread in addition to the caller. Keep the preregistered literal setting for both phases and describe it precisely; do not claim one total SQLite thread or a strict single-thread comparison. Library thread environment variables remain 1, workers remain sequential. Reference: https://www.sqlite.org/pragma.html#pragma_threads .

This clarification changes reporting, not measurements or settings. Main code and method hashes will be saved at launch. The original protocol and pre-pilot addendum remain unchanged.
