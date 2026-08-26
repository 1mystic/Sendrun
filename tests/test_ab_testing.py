"""ml/experiments/ab_testing.py — deterministic variant assignment and the
two-proportion z-test's actual statistical correctness, verified against
known reference results, not just "it returns a number."""

from __future__ import annotations

import pytest

from ml.experiments.ab_testing import (
    MIN_SAMPLE_SIZE_PER_ARM,
    ArmResult,
    assign_variant,
    summarize,
    two_proportion_z_test,
)


class TestAssignVariant:
    def test_same_pair_always_gets_the_same_variant(self):
        """The property the whole module exists to guarantee: a retry or a
        re-render must never flip a contact's assignment mid-experiment."""
        results = {assign_variant("camp_1", "contact_42") for _ in range(20)}
        assert len(results) == 1

    def test_different_contacts_can_get_different_variants(self):
        variants = {assign_variant("camp_1", f"contact_{i}") for i in range(50)}
        assert variants == {"A", "B"}  # with 50 contacts, both should appear

    def test_split_is_roughly_50_50_over_many_contacts(self):
        assignments = [assign_variant("camp_1", f"contact_{i}") for i in range(5000)]
        a_count = assignments.count("A")
        # Not an exact 50/50 (it's a hash, not a literal alternation), but
        # should be close — this is a sanity bound, not a precise assertion.
        assert 0.45 <= a_count / len(assignments) <= 0.55

    def test_custom_split_shifts_the_ratio(self):
        assignments = [
            assign_variant("camp_1", f"contact_{i}", split=0.2) for i in range(5000)
        ]
        a_count = assignments.count("A")
        assert 0.15 <= a_count / len(assignments) <= 0.25

    def test_different_campaigns_reassign_the_same_contact_independently(self):
        """A contact's variant in campaign 1 must not determine their variant
        in campaign 2 — each campaign is its own independent experiment."""
        # Not asserting a specific pair MUST differ (that would be flaky - could
        # legitimately match), just that the assignment is a function of
        # BOTH ids, not contact_id alone.
        results = {assign_variant(f"camp_{i}", "contact_x") for i in range(30)}
        assert len(results) == 2  # both A and B appear across different campaigns


class TestTwoProportionZTest:
    def test_insufficient_sample_size_reports_no_result(self):
        arm_a = ArmResult("A", sent=10, opened=5)
        arm_b = ArmResult("B", sent=10, opened=6)
        result = two_proportion_z_test(arm_a, arm_b)
        assert result.has_sufficient_data is False
        assert not result.is_significant
        assert result.winner is None

    def test_identical_arms_are_not_significant(self):
        arm_a = ArmResult("A", sent=1000, opened=300)
        arm_b = ArmResult("B", sent=1000, opened=300)
        result = two_proportion_z_test(arm_a, arm_b)
        assert result.has_sufficient_data is True
        assert not result.is_significant
        assert result.winner is None
        assert result.p_value == pytest.approx(1.0)

    def test_a_large_clear_difference_is_significant(self):
        """30% vs 45% open rate at n=1000/arm is a textbook clear win —
        verifies the z-test actually detects a real difference, not just
        that it runs without crashing."""
        arm_a = ArmResult("A", sent=1000, opened=300)   # 30%
        arm_b = ArmResult("B", sent=1000, opened=450)   # 45%
        result = two_proportion_z_test(arm_a, arm_b)
        assert result.is_significant
        assert result.winner == "B"
        assert result.p_value < 0.001  # this size of effect is overwhelmingly significant

    def test_a_small_difference_at_large_n_can_still_be_significant(self):
        """Statistical significance is about sample size AND effect size —
        even a 2-point difference becomes detectable with enough data."""
        arm_a = ArmResult("A", sent=50000, opened=15000)   # 30.0%
        arm_b = ArmResult("B", sent=50000, opened=16000)   # 32.0%
        result = two_proportion_z_test(arm_a, arm_b)
        assert result.is_significant
        assert result.winner == "B"

    def test_a_small_difference_at_small_n_is_not_significant(self):
        """The SAME 2-point difference, at a sample size where it's not
        actually distinguishable from noise, must NOT be reported as a
        winner — this is the exact false-positive a naive 'A > B' comparison
        would make."""
        arm_a = ArmResult("A", sent=150, opened=45)   # 30.0%
        arm_b = ArmResult("B", sent=150, opened=48)   # 32.0%
        result = two_proportion_z_test(arm_a, arm_b)
        assert result.has_sufficient_data is True  # both clear the min sample floor
        assert not result.is_significant

    def test_lift_is_computed_correctly(self):
        arm_a = ArmResult("A", sent=1000, opened=200)   # 20%
        arm_b = ArmResult("B", sent=1000, opened=250)   # 25%
        result = two_proportion_z_test(arm_a, arm_b)
        assert result.lift == pytest.approx(0.25, rel=0.01)  # 25% relative lift

    def test_a_can_win_when_it_is_the_higher_arm(self):
        arm_a = ArmResult("A", sent=1000, opened=450)   # 45%
        arm_b = ArmResult("B", sent=1000, opened=300)   # 30%
        result = two_proportion_z_test(arm_a, arm_b)
        assert result.winner == "A"

    def test_zero_opens_in_both_arms_does_not_crash(self):
        """An edge case a naive implementation's division would choke on."""
        arm_a = ArmResult("A", sent=500, opened=0)
        arm_b = ArmResult("B", sent=500, opened=0)
        result = two_proportion_z_test(arm_a, arm_b)
        assert not result.is_significant
        assert result.winner is None


class TestArmResult:
    def test_open_rate_computed_correctly(self):
        arm = ArmResult("A", sent=200, opened=50)
        assert arm.open_rate == pytest.approx(0.25)

    def test_open_rate_is_zero_for_zero_sends(self):
        arm = ArmResult("A", sent=0, opened=0)
        assert arm.open_rate == 0.0


class TestSummarize:
    def test_summarizes_insufficient_data(self):
        arm_a = ArmResult("A", sent=10, opened=3)
        arm_b = ArmResult("B", sent=10, opened=4)
        result = two_proportion_z_test(arm_a, arm_b)
        text = summarize(result)
        assert "Not enough data" in text
        assert str(MIN_SAMPLE_SIZE_PER_ARM) in text

    def test_summarizes_a_significant_winner(self):
        arm_a = ArmResult("A", sent=1000, opened=250)
        arm_b = ArmResult("B", sent=1000, opened=400)
        result = two_proportion_z_test(arm_a, arm_b)
        text = summarize(result)
        assert "Variant B wins" in text

    def test_summarizes_no_significant_difference(self):
        arm_a = ArmResult("A", sent=200, opened=60)
        arm_b = ArmResult("B", sent=200, opened=64)
        result = two_proportion_z_test(arm_a, arm_b)
        text = summarize(result)
        assert "No significant difference" in text
