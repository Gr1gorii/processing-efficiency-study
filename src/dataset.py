"""Deterministic synthetic inputs and a separate NumPy correctness oracle."""

import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np


def digest_result(rows, width):
    """Stream fixed-width signed integers; avoid building a giant JSON string."""
    digest = hashlib.sha256()
    digest.update(struct.pack("<QQ", len(rows), width))
    pack = struct.Struct("<" + "q" * width).pack
    for row in rows:
        digest.update(pack(*(int(value) for value in row)))
    return digest.hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate(rows, seed, dimension_rows):
    # Separate streams make the dimension identical at every fact-table size.
    rng = np.random.Generator(np.random.PCG64(seed))
    dim_rng = np.random.Generator(np.random.PCG64(seed + 1))
    fact = np.column_stack([
        np.arange(rows, dtype=np.int64),
        rng.integers(0, dimension_rows, rows, dtype=np.int64),
        rng.integers(0, 64, rows, dtype=np.int64),
        rng.integers(-1000, 10001, rows, dtype=np.int64),
        rng.integers(0, 4, rows, dtype=np.int64),
    ])
    customers = np.column_stack([
        np.arange(dimension_rows, dtype=np.int64),
        dim_rng.integers(0, 8, dimension_rows, dtype=np.int64),
    ])
    return fact, customers


def reference(fact, customers, operation):
    """NumPy reference; backend implementations do not use this function."""
    if operation == "filter":
        mask = np.logical_and(fact[:, 4] == 1, fact[:, 3] >= 5000)
        result = fact[mask][:, [0, 3]]
        return [tuple(map(int, r)) for r in result[np.argsort(result[:, 0])]]
    if operation == "group":
        keys, amounts = fact[:, 2], fact[:, 3]
    elif operation == "join":
        dim = customers[np.argsort(customers[:, 0])]
        positions = np.searchsorted(dim[:, 0], fact[:, 1])
        valid = positions < len(dim)
        valid[valid] &= dim[positions[valid], 0] == fact[valid, 1]
        keys, amounts = dim[positions[valid], 1], fact[valid, 3]
    else:
        raise ValueError(operation)
    unique, inverse = np.unique(keys, return_inverse=True)
    counts = np.zeros(len(unique), dtype=np.int64)
    sums = np.zeros(len(unique), dtype=np.int64)
    np.add.at(counts, inverse, 1)
    np.add.at(sums, inverse, amounts)
    return list(zip(map(int, unique), map(int, counts), map(int, sums)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, required=True)
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--dimension-rows", type=int, default=5000)
    parser.add_argument("--output", type=Path, default=Path("data"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for rows in args.sizes:
        path = args.output / f"synthetic_{rows}.npz"
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")
        fact, customers = generate(rows, args.seed, args.dimension_rows)
        assert len(np.unique(customers[:, 0])) == len(customers)
        assert np.isin(fact[:, 1], customers[:, 0]).all()
        expected = {}
        for operation in ["filter", "group", "join"]:
            result = reference(fact, customers, operation)
            if operation != "filter":
                assert sum(r[1] for r in result) == rows
                assert sum(r[2] for r in result) == int(fact[:, 3].sum())
            expected[operation] = {
                "sha256": digest_result(result, 2 if operation == "filter" else 3),
                "result_rows": len(result),
            }
        np.savez(path, fact=fact, customers=customers)
        manifest = {"rows": rows, "seed": args.seed, "dimension_rows": args.dimension_rows,
                    "dtype": "int64", "npz_sha256": file_sha256(path),
                    "source_bytes": path.stat().st_size, "expected": expected,
                    "fact_sum_amount_cents": int(fact[:, 3].sum()),
                    "unique_dimension_keys": True, "unmatched_fact_keys": 0}
        path.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"Generated {rows:,} rows, {path.stat().st_size / 1024**2:.2f} MiB", flush=True)


if __name__ == "__main__":
    main()
