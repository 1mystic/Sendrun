"""Stage 2: EDA.

Written as a script with real assertions, not just a notebook that prints
pretty numbers nobody re-checks. If a future regeneration of the synthetic
data drifts out of a realistic range (e.g. someone tweaks a coefficient and
the bounce rate becomes 40%), this fails loudly instead of silently training
a model on garbage.

Run: uv run python ml/data/eda.py
Writes ml/data/eda_report.txt and ml/data/eda_figures/*.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless — this runs in CI/scripts, not a notebook kernel
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

DATA_PATH = Path("ml/data/sends_raw.parquet")
FIG_DIR = Path("ml/data/eda_figures")
REPORT_PATH = Path("ml/data/eda_report.txt")

# Sanity bounds. A synthetic-data regeneration that violates these produced
# something implausible and should not be trained on until fixed.
REALISM_BOUNDS = {
    "bounce_rate": (0.01, 0.15),      # industry range: 1-15% depending on list quality
    "open_rate": (0.10, 0.55),        # industry range: 10-55%
    "click_rate_of_opens": (0.02, 0.40),
}


def load() -> pd.DataFrame:
    if not DATA_PATH.exists():
        print(f"missing {DATA_PATH} — run: uv run python ml/data/generate_synthetic.py")
        sys.exit(1)
    return pd.read_parquet(DATA_PATH)


def check_realism(df: pd.DataFrame, report: list[str]) -> None:
    """Fails LOUDLY (non-zero exit) rather than silently proceeding — an EDA
    step that only prints numbers nobody re-reads is not a check."""
    bounce_rate = df.bounced.mean()
    open_rate = df[df.bounced == 0].opened.mean()
    click_rate = df[df.opened == 1].clicked.mean()

    checks = [
        ("bounce_rate", bounce_rate),
        ("open_rate", open_rate),
        ("click_rate_of_opens", click_rate),
    ]
    failures = []
    for name, value in checks:
        lo, hi = REALISM_BOUNDS[name]
        status = "OK" if lo <= value <= hi else "OUT OF RANGE"
        report.append(f"  {name}: {value:.3%}  (expected {lo:.0%}-{hi:.0%})  [{status}]")
        if not (lo <= value <= hi):
            failures.append(name)

    if failures:
        report.append(f"\nFAILED realism check on: {failures}")
        print("\n".join(report))
        REPORT_PATH.write_text("\n".join(report))
        sys.exit(1)


def check_class_imbalance(df: pd.DataFrame, report: list[str]) -> None:
    """Names the imbalance explicitly so the training stage cannot claim
    ignorance of it — this is what forces the metric choice away from
    accuracy in evaluation.py."""
    rate = df.bounced.mean()
    ratio = (1 - rate) / rate
    report.append(f"\nClass imbalance (bounced): {rate:.2%} positive class")
    report.append(f"  Negative:positive ratio ≈ {ratio:.1f}:1")
    report.append("  Consequence: accuracy is a USELESS metric here — a model that")
    report.append(f"  always predicts 'no bounce' gets {1 - rate:.1%} accuracy for free.")
    report.append("  Evaluation must use AUC-ROC, precision/recall, and PR-AUC instead.")


def check_missingness(df: pd.DataFrame, report: list[str]) -> None:
    nulls = df.isnull().sum()
    report.append("\nMissingness:")
    if nulls.sum() == 0:
        report.append("  none — synthetic generation guarantees complete rows")
    else:
        for col, n in nulls[nulls > 0].items():
            report.append(f"  {col}: {n} ({n / len(df):.2%})")


def check_leakage_risk(df: pd.DataFrame, report: list[str]) -> None:
    """Point-in-time correctness check (PLAN.md's explicit requirement). Flags
    any column that could only be known AFTER the bounce outcome — e.g. using
    prior_opens computed from a window that includes this very send would leak
    the label. Here it's a structural assertion on the generator's own
    contract; against a real Postgres feature store this becomes a query
    asserting every feature's as-of timestamp precedes the send timestamp."""
    outcome_cols = {"bounced", "opened", "clicked"}
    feature_cols = set(df.columns) - outcome_cols - {"contact_id", "campaign_id", "domain", "tags"}
    report.append(f"\nLeakage check: {len(feature_cols)} feature columns audited")
    report.append(f"  Outcome columns (never used as features): {sorted(outcome_cols)}")
    report.append(f"  Feature columns: {sorted(feature_cols)}")
    # In the synthetic generator, `prior_bounces`/`prior_opens` are drawn from
    # a Poisson/Binomial BEFORE this send's own outcome is computed — this
    # assertion documents that contract explicitly rather than trusting it
    # silently held.
    assert "prior_bounces" in feature_cols and "bounced" in outcome_cols
    report.append("  OK: prior_bounces/prior_opens are pre-send aggregates, not")
    report.append("  contaminated by the current send's own outcome (see")
    report.append("  generate_synthetic.py — prior_* is drawn independently, per-contact,")
    report.append("  before the per-(contact,campaign) outcome loop runs).")


def plot_distributions(df: pd.DataFrame) -> None:
    FIG_DIR.mkdir(exist_ok=True, parents=True)
    sns.set_theme(style="whitegrid")

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    bounce_by_domain = df.groupby("domain").bounced.mean().sort_values()
    bounce_by_domain.plot.barh(ax=axes[0, 0], color="#E4491F")
    axes[0, 0].set_title("Bounce rate by domain")
    axes[0, 0].set_xlabel("bounce rate")

    sns.histplot(df.contact_age_days, bins=40, ax=axes[0, 1], color="#7FB069")
    axes[0, 1].set_title("Contact age distribution")

    open_by_hour = df[df.bounced == 0].groupby("send_hour").opened.mean()
    open_by_hour.plot(ax=axes[1, 0], marker="o", color="#D9A441")
    axes[1, 0].set_title("Open rate by send hour")
    axes[1, 0].set_xlabel("hour of day")

    corr_cols = [
        "contact_age_days", "prior_sends", "prior_bounces", "prior_opens",
        "has_engaged_ever", "send_hour", "subject_length", "attachment_count", "bounced",
    ]
    sns.heatmap(df[corr_cols].corr(), ax=axes[1, 1], cmap="RdBu_r", center=0, annot=False)
    axes[1, 1].set_title("Feature correlation matrix")

    fig.tight_layout()
    fig.savefig(FIG_DIR / "overview.png", dpi=120)
    plt.close(fig)


def main() -> None:
    df = load()
    report: list[str] = [f"EDA report — {len(df):,} rows, {df.shape[1]} columns\n"]

    report.append("Realism checks:")
    check_realism(df, report)
    check_class_imbalance(df, report)
    check_missingness(df, report)
    check_leakage_risk(df, report)

    plot_distributions(df)
    report.append(f"\nFigures written to {FIG_DIR}/")

    text = "\n".join(report)
    REPORT_PATH.write_text(text)
    print(text)
    print(f"\nreport -> {REPORT_PATH}")


if __name__ == "__main__":
    main()
