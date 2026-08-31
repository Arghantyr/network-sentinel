"""Generate labelled NetFlow-like records for a reproducible demo."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

NORMAL_PORTS = (53, 80, 443, 123, 22)
ANOMALOUS_PORTS = (21, 23, 445, 3389, 4444)


def _normal_records(rng: np.random.Generator, count: int) -> pd.DataFrame:
    return pd.DataFrame({
        "device_id": "pi-4", "timestamp": pd.date_range("2025-01-01", periods=count, freq="min"),
        "duration_s": rng.lognormal(1.2, 0.5, count),
        "bytes_out": rng.lognormal(8, 1, count).astype(int),
        "bytes_in": rng.lognormal(9, 1, count).astype(int),
        "packets": rng.poisson(40, count),
        "dst_port": rng.choice(NORMAL_PORTS, count, p=[.2, .15, .45, .05, .15]),
        "failed_connections": rng.poisson(.4, count), "label": 0,
    })


def _anomalous_records(rng: np.random.Generator, count: int) -> pd.DataFrame:
    return pd.DataFrame({
        "device_id": "pi-4", "timestamp": pd.date_range("2025-01-02", periods=count, freq="min"),
        "duration_s": rng.lognormal(.2, .6, count),
        "bytes_out": rng.lognormal(12, 1.2, count).astype(int),
        "bytes_in": rng.lognormal(5, 1, count).astype(int),
        "packets": rng.poisson(220, count), "dst_port": rng.choice(ANOMALOUS_PORTS, count),
        "failed_connections": rng.poisson(8, count), "label": 1,
    })


def generate(n_normal: int = 1200, n_anomaly: int = 180, seed: int = 7) -> pd.DataFrame:
    """Create deterministic labelled data; labels are for evaluation only."""
    rng = np.random.default_rng(seed)
    records = pd.concat([_normal_records(rng, n_normal), _anomalous_records(rng, n_anomaly)])
    return records.sort_values("timestamp").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/flows.csv")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    generate(seed=args.seed).to_csv(output, index=False)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
