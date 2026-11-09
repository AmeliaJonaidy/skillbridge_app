"""Outcome-calibrated compatibility scoring.

The weighted matcher remains the source of truth until enough real application
outcomes exist to train a model. This keeps early scores useful and explainable.
"""

from functools import lru_cache

from django.apps import apps

MIN_TRAINING_EXAMPLES = 10


def _features(breakdown):
    skill = breakdown.get("skill_match", {})
    evidence = breakdown.get("evidence_match", {})
    return [
        float(skill.get("earned", 0)) / max(float(skill.get("max", 1)), 1),
        float(evidence.get("earned", 0)) / max(float(evidence.get("max", 1)), 1),
    ]


def _label(status):
    return 100.0 if status in {"shortlisted", "interview", "offer"} else 0.0


@lru_cache(maxsize=1)
def _trained_model(example_count):
    if example_count < MIN_TRAINING_EXAMPLES:
        return None
    try:
        from sklearn.ensemble import RandomForestRegressor
    except ImportError:
        return None

    Application = apps.get_model("applications", "JobApplication")
    examples = list(
        Application.objects.exclude(match_breakdown={})
        .exclude(status="withdrawn")
        .values("match_breakdown", "status")[:5000]
    )
    if len(examples) < MIN_TRAINING_EXAMPLES:
        return None
    model = RandomForestRegressor(
        n_estimators=50,
        max_depth=4,
        random_state=42,
        min_samples_leaf=2,
    )
    model.fit(
        [_features(item["match_breakdown"]) for item in examples],
        [_label(item["status"]) for item in examples],
    )
    return model


def predict_compatibility(breakdown, fallback_score):
    """Return an ML-calibrated score and explanation when data is sufficient."""
    Application = apps.get_model("applications", "JobApplication")
    example_count = Application.objects.exclude(match_breakdown={}).exclude(status="withdrawn").count()
    model = _trained_model(example_count)
    if model is None:
        return fallback_score, {
            "mode": "weighted",
            "reason": "Using the explainable weighted score until at least 10 real application outcomes are available.",
        }
    prediction = max(0, min(100, round(float(model.predict([_features(breakdown)])[0]))))
    return prediction, {
        "mode": "ml",
        "reason": f"Calibrated from {example_count} recorded application outcomes.",
    }
