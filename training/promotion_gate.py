"""Model promotion gate: Candidate -> Validated -> Production.

The gate never runs itself automatically against "better metrics" — it
compares a candidate's TEST metrics against configurable minimum
thresholds and, if a production model already exists, against that
production model's metrics with a regression tolerance. See
params.yaml `evaluation.promotion_gates` for the values and an explicit
note that they are engineering acceptance criteria, not scientific truths.

Passing this gate only makes a model eligible to move from Candidate to
Validated. Validated -> Production is a separate, explicit, non-automatic
action (training/promote_model.py) — this module never sets a model to
Production itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field

GATE_METRICS = ["pr_auc", "recall", "precision", "f1", "roc_auc"]


@dataclass
class GateCheck:
    metric: str
    check_type: str  # "minimum_threshold" | "regression_tolerance"
    candidate_value: float
    reference_value: float | None
    passed: bool
    detail: str


@dataclass
class GateResult:
    passed: bool
    checks: list[GateCheck] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [
                {"metric": c.metric, "check_type": c.check_type, "candidate_value": c.candidate_value,
                 "reference_value": c.reference_value, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
        }


def evaluate_promotion_gate(
    candidate_test_metrics: dict,
    production_test_metrics: dict | None,
    gate_config: dict,
) -> GateResult:
    """candidate_test_metrics / production_test_metrics: dicts with at
    least the keys in GATE_METRICS (e.g. the output of
    training.evaluate.compute_metrics on the TEST split).
    """
    checks: list[GateCheck] = []
    thresholds = gate_config["minimum_thresholds"]

    for metric in GATE_METRICS:
        min_key = f"min_{metric}"
        min_value = thresholds[min_key]
        candidate_value = candidate_test_metrics[metric]
        passed = candidate_value >= min_value
        checks.append(GateCheck(
            metric=metric, check_type="minimum_threshold",
            candidate_value=candidate_value, reference_value=min_value, passed=passed,
            detail=f"{metric}={candidate_value:.4f} {'>=' if passed else '<'} minimum {min_value}",
        ))

    if production_test_metrics is not None:
        tolerance = gate_config["regression_tolerance"]
        for metric in GATE_METRICS:
            candidate_value = candidate_test_metrics[metric]
            production_value = production_test_metrics[metric]
            allowed_tol = tolerance[metric]
            regression = production_value - candidate_value
            passed = regression <= allowed_tol
            checks.append(GateCheck(
                metric=metric, check_type="regression_tolerance",
                candidate_value=candidate_value, reference_value=production_value, passed=passed,
                detail=(f"{metric}: candidate={candidate_value:.4f} vs production={production_value:.4f} "
                        f"(regression={regression:.4f}, allowed<={allowed_tol})"),
            ))

    return GateResult(passed=all(c.passed for c in checks), checks=checks)
