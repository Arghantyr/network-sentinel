"""Train the baseline anomaly detector."""
from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features import make_features

RANDOM_SEED = 7


def train(records: pd.DataFrame) -> Pipeline:
    """Fit an unsupervised detector using only labelled normal baseline data."""
    if "label" not in records.columns:
        raise ValueError("Training data must contain a 'label' column.")
    baseline = records.loc[records["label"] == 0]
    if baseline.empty:
        raise ValueError("Training data must include normal (label=0) records.")

    model = Pipeline([
        ("scale", StandardScaler()),
        ("detector", IsolationForest(n_estimators=200, contamination="auto", random_state=RANDOM_SEED)),
    ])
    model.fit(make_features(baseline))
    return model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="CSV with labelled flow-like records")
    parser.add_argument("--model", required=True, help="Destination .joblib model path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = train(pd.read_csv(args.input))
    output = Path(args.model)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output)
    print(f"Wrote model to {output}")


if __name__ == "__main__":
    main()
