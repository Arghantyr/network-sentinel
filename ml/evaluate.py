"""Evaluate a saved anomaly detector against labelled records."""
from __future__ import annotations

import argparse

import joblib
import pandas as pd
from sklearn.metrics import average_precision_score, classification_report, confusion_matrix

from .features import make_features


def evaluate(records: pd.DataFrame, model: object) -> dict[str, object]:
    """Return classification metrics; labels are required only for evaluation."""
    if "label" not in records.columns:
        raise ValueError("Evaluation data must contain a 'label' column.")
    features = make_features(records)
    predicted_anomaly = (model.predict(features) == -1).astype(int)
    anomaly_score = -model.decision_function(features)
    return {
        "report": classification_report(records["label"], predicted_anomaly, target_names=["normal", "anomaly"]),
        "confusion_matrix": confusion_matrix(records["label"], predicted_anomaly),
        "average_precision": average_precision_score(records["label"], anomaly_score),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    result = evaluate(pd.read_csv(args.input), joblib.load(args.model))
    print(result["report"])
    print("confusion_matrix:\n", result["confusion_matrix"])
    print("average_precision:", round(float(result["average_precision"]), 4))


if __name__ == "__main__":
    main()
