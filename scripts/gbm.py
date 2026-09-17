"""Portable, dependency-free evaluator for the exported xpts-v2 model.

The model is trained offline with scikit-learn and exported to a plain JSON of
decision trees (see train_model.py). This module loads that JSON and scores it
with pure Python, so the live pipeline needs **no** ML libraries — it just reads
data/model_v2.json and evaluates.

Prediction = init + learning_rate · Σ tree(features), each tree a CART walked by
threshold comparisons.
"""
from __future__ import annotations

import json
import os


def load_model(path):
    """Load an exported model, or None if it's absent/unreadable."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            m = json.load(fh)
        if m.get("features") and m.get("trees"):
            return m
    except (OSError, ValueError):
        pass
    return None


def predict(model, feat_list):
    """Score one ordered feature vector (same order as model['features'])."""
    total = model["init"]
    lr = model["learning_rate"]
    for t in model["trees"]:
        left, right = t["left"], t["right"]
        feat, thr, val = t["feature"], t["threshold"], t["value"]
        node = 0
        while left[node] != -1:                       # -1 marks a leaf
            node = left[node] if feat_list[feat[node]] <= thr[node] else right[node]
        total += lr * val[node]
    return total
