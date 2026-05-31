"""
Bias Metrics — measures AI prediction fairness across demographic groups.

Computes three standard algorithmic fairness metrics:

1. Demographic Parity Difference
   | P(ŷ=1|A=a) - P(ŷ=1|A=b) | across all group pairs.
   → Measures whether approval rates are equal across groups.

2. Disparate Impact Ratio
   min(P(ŷ=1|A=a)) / max(P(ŷ=1|A=b))
   → EEOC "4/5ths rule": ratio < 0.8 is flagged.

3. Equalized Odds
   Difference in True Positive Rate across groups.
   → Measures whether the model is equally accurate for all groups.

Healthcare context: used to detect demographic disparities in
AI-assisted claims adjudication or prior authorization decisions.
A disparity > 10% triggers a flag for human review.
"""
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# Flagging thresholds
DISPARITY_THRESHOLD = 0.10   # >10% worse outcomes vs best group
DISPARATE_IMPACT_THRESHOLD = 0.80  # EEOC 4/5ths rule


@dataclass
class GroupMetrics:
    group: str
    n_total: int
    n_positive: int
    approval_rate: float
    true_positive_rate: Optional[float] = None  # Requires ground truth labels


@dataclass
class BiasReport:
    total_predictions: int
    group_metrics: List[GroupMetrics]
    demographic_parity_difference: float
    disparate_impact_ratio: float
    equalized_odds_difference: Optional[float]
    flagged_groups: List[str]
    compliant: bool
    summary: str


class BiasMetrics:
    """
    Fairness metrics for AI predictions across demographic groups.

    Usage:
        bm = BiasMetrics()

        # predictions: list of 0/1 (denied/approved)
        # groups: list of group labels (one per prediction)
        # labels: optional ground truth (for equalized odds)

        report = bm.compute(
            predictions=[1, 0, 1, 1, 0],
            groups=["GroupA", "GroupB", "GroupA", "GroupB", "GroupA"],
            labels=[1, 0, 1, 0, 0],
        )
    """

    def __init__(
        self,
        disparity_threshold: float = DISPARITY_THRESHOLD,
        disparate_impact_threshold: float = DISPARATE_IMPACT_THRESHOLD,
    ):
        self.disparity_threshold = disparity_threshold
        self.disparate_impact_threshold = disparate_impact_threshold

    def _group_approval_rates(
        self,
        predictions: List[int],
        groups: List[str],
    ) -> Dict[str, GroupMetrics]:
        """Compute per-group approval rates."""
        group_data: Dict[str, List[int]] = {}
        for pred, grp in zip(predictions, groups):
            group_data.setdefault(grp, []).append(pred)

        metrics: Dict[str, GroupMetrics] = {}
        for grp, preds in group_data.items():
            n_total = len(preds)
            n_positive = sum(preds)
            metrics[grp] = GroupMetrics(
                group=grp,
                n_total=n_total,
                n_positive=n_positive,
                approval_rate=round(n_positive / n_total, 4) if n_total > 0 else 0.0,
            )
        return metrics

    def _demographic_parity_difference(self, group_metrics: Dict[str, GroupMetrics]) -> float:
        """Max approval rate - min approval rate across all groups."""
        rates = [m.approval_rate for m in group_metrics.values()]
        if len(rates) < 2:
            return 0.0
        return round(max(rates) - min(rates), 4)

    def _disparate_impact_ratio(self, group_metrics: Dict[str, GroupMetrics]) -> float:
        """
        min_approval_rate / max_approval_rate.
        Per EEOC 4/5ths rule: < 0.8 indicates adverse impact.
        """
        rates = [m.approval_rate for m in group_metrics.values()]
        if len(rates) < 2 or max(rates) == 0:
            return 1.0
        return round(min(rates) / max(rates), 4)

    def _equalized_odds(
        self,
        predictions: List[int],
        labels: List[int],
        groups: List[str],
    ) -> Optional[float]:
        """
        Max difference in True Positive Rate (TPR) across groups.
        Requires ground truth labels.
        """
        tpr_by_group: Dict[str, float] = {}
        for grp in set(groups):
            indices = [i for i, g in enumerate(groups) if g == grp]
            group_preds = [predictions[i] for i in indices]
            group_labels = [labels[i] for i in indices]

            positives = [i for i, l in enumerate(group_labels) if l == 1]
            if not positives:
                continue
            tp = sum(1 for i in positives if group_preds[i] == 1)
            tpr_by_group[grp] = round(tp / len(positives), 4)

        if len(tpr_by_group) < 2:
            return None
        tprs = list(tpr_by_group.values())
        return round(max(tprs) - min(tprs), 4)

    def _flag_groups(self, group_metrics: Dict[str, GroupMetrics]) -> List[str]:
        """Identify groups with >threshold worse outcomes than best group."""
        rates = {g: m.approval_rate for g, m in group_metrics.items()}
        best_rate = max(rates.values()) if rates else 0.0
        flagged = [
            grp
            for grp, rate in rates.items()
            if (best_rate - rate) > self.disparity_threshold
        ]
        return flagged

    def compute(
        self,
        predictions: List[int],
        groups: List[str],
        labels: Optional[List[int]] = None,
        report_period: str = "last_30_days",
    ) -> BiasReport:
        """
        Compute all fairness metrics and return a structured BiasReport.

        Args:
            predictions: Binary AI decisions (1=approved/positive, 0=denied/negative)
            groups: Demographic group label per prediction
            labels: Optional ground truth for equalized odds
            report_period: Label for the reporting window
        """
        if len(predictions) != len(groups):
            raise ValueError("predictions and groups must have the same length")
        if labels and len(labels) != len(predictions):
            raise ValueError("labels must have the same length as predictions")

        group_metrics = self._group_approval_rates(predictions, groups)
        dp_diff = self._demographic_parity_difference(group_metrics)
        di_ratio = self._disparate_impact_ratio(group_metrics)
        eq_odds = self._equalized_odds(predictions, labels, groups) if labels else None
        flagged = self._flag_groups(group_metrics)

        compliant = (
            dp_diff <= self.disparity_threshold
            and di_ratio >= self.disparate_impact_threshold
        )

        if flagged:
            summary = (
                f"⚠️  Bias detected. Groups with >10% disparity: {', '.join(flagged)}. "
                f"Demographic parity difference: {dp_diff:.1%}. "
                f"Disparate impact ratio: {di_ratio:.2f} ({'FAIL' if di_ratio < 0.8 else 'PASS'})."
            )
        else:
            summary = (
                f"✅ No significant bias detected. "
                f"Demographic parity difference: {dp_diff:.1%}. "
                f"Disparate impact ratio: {di_ratio:.2f}."
            )

        logger.info(f"Bias report computed: DP diff={dp_diff}, DI ratio={di_ratio}, Flagged={flagged}")

        return BiasReport(
            total_predictions=len(predictions),
            group_metrics=list(group_metrics.values()),
            demographic_parity_difference=dp_diff,
            disparate_impact_ratio=di_ratio,
            equalized_odds_difference=eq_odds,
            flagged_groups=flagged,
            compliant=compliant,
            summary=summary,
        )

    def compute_from_audit_logs(self, audit_logs: List[dict]) -> Optional[BiasReport]:
        """
        Generate a bias report from stored audit log entries.
        Requires audit logs to have 'demographic_group' and 'outcome' fields.
        Returns None if insufficient data.
        """
        valid = [
            log for log in audit_logs
            if log.get("demographic_group") and log.get("outcome") is not None
        ]
        if len(valid) < 10:
            logger.warning(f"Insufficient data for bias report: {len(valid)} records (min 10)")
            return None

        predictions = [int(log["outcome"]) for log in valid]
        groups = [log["demographic_group"] for log in valid]
        return self.compute(predictions, groups)
