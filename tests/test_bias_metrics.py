"""
Tests for BiasMetrics.
Validates fairness metric computations with known synthetic datasets.
"""
import pytest
from app.bias_metrics import BiasMetrics, DISPARATE_IMPACT_THRESHOLD


@pytest.fixture
def bm():
    return BiasMetrics()


# ---------------------------------------------------------------------------
# Perfectly fair dataset
# ---------------------------------------------------------------------------
FAIR_PREDICTIONS = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]  # 50% approval
FAIR_GROUPS =      ["A", "B", "A", "B", "A", "B", "A", "B", "A", "B"]


# ---------------------------------------------------------------------------
# Biased dataset — Group B significantly worse than Group A
# ---------------------------------------------------------------------------
# Group A: 8/10 approved (80%)
# Group B: 3/10 approved (30%) → 50% disparity, flagged
BIASED_PREDICTIONS = [1,1,1,1,1,1,1,1,0,0,  1,1,1,0,0,0,0,0,0,0]
BIASED_GROUPS      = ["A"]*10 + ["B"]*10


class TestDemographicParity:
    def test_fair_dataset_low_disparity(self, bm):
        report = bm.compute(FAIR_PREDICTIONS, FAIR_GROUPS)
        assert report.demographic_parity_difference <= 0.10

    def test_biased_dataset_high_disparity(self, bm):
        report = bm.compute(BIASED_PREDICTIONS, BIASED_GROUPS)
        assert report.demographic_parity_difference > 0.10

    def test_single_group_zero_disparity(self, bm):
        """Single group should always show 0 disparity."""
        preds = [1, 0, 1, 1, 0]
        groups = ["A"] * 5
        report = bm.compute(preds, groups)
        assert report.demographic_parity_difference == 0.0


class TestDisparateImpact:
    def test_fair_dataset_passes_eeoc(self, bm):
        """4/5ths rule: ratio >= 0.8 for fair dataset."""
        report = bm.compute(FAIR_PREDICTIONS, FAIR_GROUPS)
        assert report.disparate_impact_ratio >= DISPARATE_IMPACT_THRESHOLD

    def test_biased_dataset_fails_eeoc(self, bm):
        """Biased dataset should fail the 4/5ths rule (ratio < 0.8)."""
        report = bm.compute(BIASED_PREDICTIONS, BIASED_GROUPS)
        assert report.disparate_impact_ratio < DISPARATE_IMPACT_THRESHOLD

    def test_ratio_never_exceeds_1(self, bm):
        report = bm.compute(FAIR_PREDICTIONS, FAIR_GROUPS)
        assert report.disparate_impact_ratio <= 1.0


class TestFlaggedGroups:
    def test_fair_dataset_no_flagged_groups(self, bm):
        report = bm.compute(FAIR_PREDICTIONS, FAIR_GROUPS)
        assert len(report.flagged_groups) == 0

    def test_biased_dataset_flags_worse_group(self, bm):
        report = bm.compute(BIASED_PREDICTIONS, BIASED_GROUPS)
        # Group B should be flagged (30% vs 80% approval)
        assert "B" in report.flagged_groups

    def test_compliant_flag_set_correctly(self, bm):
        fair_report = bm.compute(FAIR_PREDICTIONS, FAIR_GROUPS)
        biased_report = bm.compute(BIASED_PREDICTIONS, BIASED_GROUPS)
        assert fair_report.compliant is True
        assert biased_report.compliant is False


class TestInputValidation:
    def test_mismatched_lengths_raise_error(self, bm):
        with pytest.raises(ValueError, match="same length"):
            bm.compute([1, 0, 1], ["A", "B"])  # 3 preds, 2 groups

    def test_labels_length_mismatch_raises_error(self, bm):
        with pytest.raises(ValueError, match="same length"):
            bm.compute([1, 0], ["A", "B"], labels=[1])

    def test_minimum_dataset_works(self, bm):
        report = bm.compute([1], ["A"])
        assert report.total_predictions == 1


class TestEqualizedOdds:
    def test_equalized_odds_computed_with_labels(self, bm):
        predictions = [1, 0, 1, 0, 1, 0]
        groups =      ["A", "A", "A", "B", "B", "B"]
        labels =      [1, 0, 1, 1, 0, 0]
        report = bm.compute(predictions, groups, labels=labels)
        assert report.equalized_odds_difference is not None
        assert 0.0 <= report.equalized_odds_difference <= 1.0

    def test_equalized_odds_none_without_labels(self, bm):
        report = bm.compute(FAIR_PREDICTIONS, FAIR_GROUPS)
        assert report.equalized_odds_difference is None
