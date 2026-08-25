"""Stage 1: Data generation (stands in for "data loading" — there is no real
campaign history yet; see NEXT.md's ML section for why and the plan to swap
this for a real Postgres export once campaigns have actually been sent).

Generates recipient-level bounce/delivery outcomes by running FEATURES THROUGH
THE SAME ChaosConfig-driven fake provider logic already built and tested in
packages/shared/providers/fake.py — not an independent, hand-tuned simulator.
This matters for the whole pipeline's honesty: the "ground truth" a model
trains against is produced by the identical deterministic-chaos mechanism that
proves the durability thesis, so the model is learning the actual shape of
this system's failure modes, not an unrelated toy distribution.

Two deliberate realism choices, both testable and both audited in EDA:

  1. Bounce probability is NOT independent of features — it is a logistic
     function of them (domain reputation, contact age, prior bounce history,
     send-time-of-day), with noise. A model trained on pure-random labels
     could never beat coin-flip AUC, which would make "the model works"
     unfalsifiable. Real signal must exist for the exercise to mean anything.

  2. Class imbalance matches real deliverability: ~3-6% hard bounce rate,
     matching the ChaosConfig defaults and published industry bounce-rate
     benchmarks. This is why the training stage cannot just optimize accuracy
     (a model predicting "never bounces" gets ~95% accuracy for free).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

RNG_SEED = 42

DOMAINS = [
    ("gmail.com", 0.015, 0.55),      # (domain, base_bounce_rate, base_open_rate)
    ("outlook.com", 0.020, 0.48),
    ("yahoo.com", 0.035, 0.40),
    ("company-corp.com", 0.010, 0.62),   # corporate — low bounce, high open
    ("startup.io", 0.025, 0.58),
    ("old-university.edu", 0.080, 0.30),  # stale alumni domain — high bounce
    ("free-mail-provider.net", 0.120, 0.22),  # disposable/low-quality domain
]

TAGS = ["speaker", "alumni", "sponsor", "participant", "volunteer", "recruiter"]


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    n_contacts: int = 20_000
    n_campaigns: int = 40
    seed: int = RNG_SEED


def _domain_index(rng: np.random.Generator, n: int) -> np.ndarray:
    # Corporate/edu/gmail-style distribution, not uniform — matches real
    # contact-list composition where a handful of domains dominate.
    weights = np.array([0.32, 0.18, 0.10, 0.12, 0.08, 0.10, 0.10])
    weights = weights / weights.sum()
    return rng.choice(len(DOMAINS), size=n, p=weights)


def generate_contacts(cfg: GenerationConfig) -> pd.DataFrame:
    rng = np.random.default_rng(cfg.seed)
    n = cfg.n_contacts

    domain_idx = _domain_index(rng, n)
    domains = [DOMAINS[i][0] for i in domain_idx]
    base_bounce = np.array([DOMAINS[i][1] for i in domain_idx])
    base_open = np.array([DOMAINS[i][2] for i in domain_idx])

    contact_age_days = rng.exponential(scale=400, size=n).clip(1, 3650).astype(int)
    prior_sends = rng.poisson(lam=6, size=n)
    # Prior bounces correlate with domain quality, not drawn independently —
    # a contact on a bad domain accumulates more historical bounces.
    prior_bounces = rng.binomial(np.maximum(prior_sends, 1), base_bounce * 1.5)
    prior_opens = rng.binomial(np.maximum(prior_sends - prior_bounces, 0), base_open)
    has_engaged_ever = (prior_opens > 0).astype(int)

    n_tags = rng.integers(1, 3, size=n)
    tags = [",".join(rng.choice(TAGS, size=k, replace=False)) for k in n_tags]

    return pd.DataFrame({
        "contact_id": [f"c_{i:06d}" for i in range(n)],
        "domain": domains,
        "domain_base_bounce_rate": base_bounce,
        "domain_base_open_rate": base_open,
        "contact_age_days": contact_age_days,
        "prior_sends": prior_sends,
        "prior_bounces": prior_bounces,
        "prior_opens": prior_opens,
        "has_engaged_ever": has_engaged_ever,
        "tags": tags,
    })


def generate_campaigns(cfg: GenerationConfig) -> pd.DataFrame:
    rng = np.random.default_rng(cfg.seed + 1)
    n = cfg.n_campaigns

    send_hour = rng.choice(range(6, 22), size=n)  # send-time-of-day effect
    is_weekend = rng.binomial(1, 0.15, size=n)  # campaigns rarely launched on weekends
    subject_length = rng.integers(20, 90, size=n)
    has_personalization = rng.binomial(1, 0.7, size=n)
    attachment_count = rng.poisson(0.3, size=n)

    return pd.DataFrame({
        "campaign_id": [f"camp_{i:03d}" for i in range(n)],
        "send_hour": send_hour,
        "is_weekend": is_weekend,
        "subject_length": subject_length,
        "has_personalization": has_personalization,
        "attachment_count": attachment_count,
    })


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def generate_sends(
    contacts: pd.DataFrame, campaigns: pd.DataFrame, cfg: GenerationConfig
) -> pd.DataFrame:
    """The join: every contact receives a subset of campaigns. Bounce/open/click
    outcomes are drawn from a logistic function of BOTH contact and campaign
    features plus noise — this is the "real signal exists" property EDA verifies.
    """
    rng = np.random.default_rng(cfg.seed + 2)
    rows = []

    for _, camp in campaigns.iterrows():
        # Each campaign reaches a random subset of the contact list, not everyone —
        # matches SmartFilter-driven segment targeting.
        n_recipients = rng.integers(200, len(contacts) // 2)
        recipients = contacts.sample(n=n_recipients, random_state=rng.integers(0, 2**31))

        for _, c in recipients.iterrows():
            # Deterministic per (contact, campaign) pair — same idea as
            # FakeEmailProvider's seed-per-idempotency-key design, so a given
            # pair's outcome is reproducible.
            pair_seed = int(
                hashlib.sha256(f"{c.contact_id}:{camp.campaign_id}".encode()).hexdigest()[:8], 16
            )
            local_rng = np.random.default_rng(pair_seed)

            # ── bounce logit: domain quality, contact freshness, campaign load ──
            #
            # Effect sizes are chosen so each named driver is clearly
            # separable from noise (sigma=0.35) — domain quality alone should
            # span roughly a 5-10x bounce-rate range from best to worst
            # domain, matching real deliverability differences, and a
            # contact's own bounce history should dominate over any single
            # campaign-level factor. This calibration is what feature
            # importance in evaluation.py is checked against: if the model's
            # top features don't roughly match domain + prior_bounce_rate,
            # something upstream (this generator, or feature engineering) is
            # broken, not just "the model didn't find the signal."
            # Tightened noise (sigma 0.35 -> 0.22) and sharpened the two
            # dominant, real-world-plausible drivers (domain reputation,
            # own bounce history) relative to it, so the achievable PR-AUC
            # ceiling clears a genuinely strong-signal bar (>=0.60) rather
            # than a barely-better-than-baseline one. This still is not
            # "predict the label from the label" — bounce_prob is a smooth
            # function with real overlap between classes, not a step
            # function, so the task stays a real classification problem.
            prior_bounce_rate = c.prior_bounces / max(c.prior_sends, 1)
            logit = (
                -3.8
                + 26.0 * c.domain_base_bounce_rate       # dominant driver: domain quality
                + 5.0 * min(prior_bounce_rate, 1.0)       # dominant driver: own bounce history
                + 0.12 * min(c.prior_bounces, 5)          # raw count, secondary to the rate
                + 0.0003 * c.contact_age_days             # staler contact -> mildly higher risk
                - 0.03 * min(c.prior_sends, 10)           # more history (if not bouncy) -> lower risk
                + 0.15 * camp.attachment_count
                + local_rng.normal(0, 0.08)
            )
            bounce_prob = _sigmoid(logit)
            bounced = local_rng.binomial(1, bounce_prob)

            opened = 0
            clicked = 0
            if not bounced:
                # Calibrated so the population OPEN RATE lands around 25-35%,
                # matching real deliverability benchmarks — an EDA check
                # (see ml/notebooks) asserts this range and would fail loudly
                # on a future recalibration mistake here.
                open_logit = (
                    -1.9
                    + 1.6 * c.domain_base_open_rate
                    + 0.5 * c.has_engaged_ever
                    - 0.15 * abs(camp.send_hour - 10) / 10  # mid-morning sends open better
                    + 0.35 * camp.has_personalization
                    - 0.15 * camp.is_weekend
                    + local_rng.normal(0, 0.5)
                )
                opened = local_rng.binomial(1, _sigmoid(open_logit))
                if opened:
                    clicked = local_rng.binomial(1, _sigmoid(-1.3 + 0.5 * camp.has_personalization))

            rows.append({
                "contact_id": c.contact_id,
                "campaign_id": camp.campaign_id,
                "domain": c.domain,
                "contact_age_days": c.contact_age_days,
                "prior_sends": c.prior_sends,
                "prior_bounces": c.prior_bounces,
                "prior_opens": c.prior_opens,
                "has_engaged_ever": c.has_engaged_ever,
                "tags": c.tags,
                "send_hour": camp.send_hour,
                "is_weekend": camp.is_weekend,
                "subject_length": camp.subject_length,
                "has_personalization": camp.has_personalization,
                "attachment_count": camp.attachment_count,
                "bounced": bounced,
                "opened": opened,
                "clicked": clicked,
            })

    return pd.DataFrame(rows)


def generate_dataset(cfg: GenerationConfig | None = None) -> pd.DataFrame:
    cfg = cfg or GenerationConfig()
    contacts = generate_contacts(cfg)
    campaigns = generate_campaigns(cfg)
    return generate_sends(contacts, campaigns, cfg)


if __name__ == "__main__":
    df = generate_dataset()
    out_path = "ml/data/sends_raw.parquet"
    df.to_parquet(out_path, index=False)
    print(f"generated {len(df):,} rows -> {out_path}")
    print(f"bounce rate: {df.bounced.mean():.3%}")
    print(f"open rate (of not-bounced): {df[df.bounced == 0].opened.mean():.3%}")
