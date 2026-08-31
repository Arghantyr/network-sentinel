import pandas as pd
import pytest

from ml.evaluate import evaluate
from ml.features import FEATURE_COLUMNS, make_features
from ml.simulator import generate
from ml.train import train


def test_feature_shape_and_columns():
    records = generate(n_normal=3, n_anomaly=2)
    features = make_features(records)
    assert tuple(features.columns) == FEATURE_COLUMNS
    assert features.shape == (5, len(FEATURE_COLUMNS))


def test_missing_feature_is_explained():
    with pytest.raises(ValueError, match="bytes_out"):
        make_features(pd.DataFrame({"duration_s": [1]}))


def test_end_to_end_model_has_useful_ranking():
    records = generate()
    result = evaluate(records, train(records))
    assert result["average_precision"] > 0.80
