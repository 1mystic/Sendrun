"""packages/shared/preflight.py in isolation — pure function, no DB, no
network. Each check is tested for both the ok and the triggered case, since a
heuristic that never fires is worse than useless (false confidence)."""

from __future__ import annotations

import uuid

from packages.shared.models import Contact, TemplateVersion
from packages.shared.preflight import run_preflight


def _template(
    subject: str, html_body: str, variables: list[str], text_body: str | None = None
) -> TemplateVersion:
    return TemplateVersion(
        id=uuid.uuid4(), template_id=uuid.uuid4(), version=1,
        subject=subject, html_body=html_body, text_body=text_body, variables=variables,
    )


def _contact(email: str, name: str | None = None, **fields: str) -> Contact:
    return Contact(id=uuid.uuid4(), org_id=uuid.uuid4(), email=email, name=name, fields=fields)


class TestSpamRisk:
    def test_a_clean_template_scores_low(self):
        t = _template("Speak at AI Hackathon 2026, {{first_name}}?",
                       "<p>Hi {{first_name}}, join us for a talk on {{topic}}.</p>",
                       ["first_name", "topic"])
        report = run_preflight(t, [_contact("a@example.com", "A", topic="ML")])
        assert report.spam_risk < 30

    def test_promotional_keywords_raise_the_score(self):
        t = _template("FREE prize! Act now, click here!!",
                       "<p>Buy now, guaranteed winner, no obligation cash prize.</p>", [])
        report = run_preflight(t, [_contact("a@example.com")])
        assert report.spam_risk > 30
        fired = [s.name for s in report.spam_signals if s.triggered]
        assert "promotional_keywords" in fired

    def test_all_caps_subject_is_flagged(self):
        t = _template("URGENT ACT NOW BEFORE ITS TOO LATE", "<p>hi</p>", [])
        report = run_preflight(t, [_contact("a@example.com")])
        fired = {s.name for s in report.spam_signals if s.triggered}
        assert "subject_all_caps" in fired

    def test_excessive_exclamation_marks_are_flagged(self):
        t = _template("Hello there!! Amazing!!", "<p>hi</p>", [])
        report = run_preflight(t, [_contact("a@example.com")])
        fired = {s.name for s in report.spam_signals if s.triggered}
        assert "excessive_punctuation" in fired

    def test_high_link_density_is_flagged(self):
        links = " ".join(f'<a href="https://x.com/{i}">link{i}</a>' for i in range(6))
        t = _template("Check these out", f"<p>{links}</p>", [])
        report = run_preflight(t, [_contact("a@example.com")])
        fired = {s.name for s in report.spam_signals if s.triggered}
        assert "link_density" in fired

    def test_score_is_capped_at_100(self):
        t = _template(
            "FREE FREE FREE ACT NOW URGENT!!!!! CLICK HERE BUY NOW GUARANTEE",
            " ".join(f'<a href="https://x.com/{i}">click</a>' for i in range(20)), [],
        )
        report = run_preflight(t, [_contact("a@example.com")])
        assert report.spam_risk <= 100

    def test_every_signal_has_a_human_readable_explanation(self):
        """The whole point of a heuristic score over an opaque model output —
        every signal must be independently checkable."""
        t = _template("FREE prize!!", "<p>click here</p>", [])
        report = run_preflight(t, [_contact("a@example.com")])
        for signal in report.spam_signals:
            assert signal.explanation
            assert isinstance(signal.explanation, str)


class TestPersonalization:
    def test_full_personalization_scores_100(self):
        t = _template(
            "Hi {{first_name}}", "<p>{{first_name}} re {{topic}}</p>", ["first_name", "topic"]
        )
        contacts = [
            _contact("a@example.com", "Alice", topic="AI"),
            _contact("b@example.com", "Bob", topic="ML"),
        ]
        report = run_preflight(t, contacts)
        assert report.personalization_score == 100
        assert report.recipients_missing_variables == {}

    def test_missing_variable_drops_the_score_and_names_the_recipient(self):
        t = _template("Hi {{first_name}}", "<p>Re: {{topic}}</p>", ["first_name", "topic"])
        contacts = [
            _contact("complete@example.com", "Alice", topic="AI"),
            _contact("missing@example.com", "Bob"),  # no topic field
        ]
        report = run_preflight(t, contacts)
        assert report.personalization_score == 50
        assert report.recipients_missing_variables == {"missing@example.com": ["topic"]}

    def test_first_name_is_derived_from_contact_name_when_not_a_field(self):
        """first_name is special-cased: it comes from Contact.name, not a
        Contact.fields entry — a contact created via the UI (name only, no
        custom fields) must not be flagged as incomplete for {{first_name}}."""
        t = _template("Hi {{first_name}}", "<p>hi</p>", ["first_name"])
        report = run_preflight(t, [_contact("a@example.com", "Rahul Menon")])
        assert report.recipients_missing_variables == {}

    def test_no_declared_variables_means_everyone_is_complete(self):
        t = _template("Hi there", "<p>a generic message</p>", [])
        contacts = [_contact("a@example.com"), _contact("b@example.com")]
        report = run_preflight(t, contacts)
        assert report.personalization_score == 100


class TestLinks:
    def test_valid_links_pass(self):
        t = _template("Hi", '<p><a href="https://sendrun.app/x">link</a></p>', [])
        report = run_preflight(t, [_contact("a@example.com")])
        link_check = next(c for c in report.checks if c.id == "links")
        assert link_check.severity == "ok"

    def test_broken_link_is_flagged_critical(self):
        t = _template("Hi", '<p><a href="javascript:alert(1)">click</a></p>', [])
        report = run_preflight(t, [_contact("a@example.com")])
        link_check = next(c for c in report.checks if c.id == "links")
        assert link_check.severity == "crit"

    def test_no_links_is_not_an_error(self):
        t = _template("Hi", "<p>plain text, no links</p>", [])
        report = run_preflight(t, [_contact("a@example.com")])
        link_check = next(c for c in report.checks if c.id == "links")
        assert link_check.severity == "ok"


class TestBounceRisk:
    def test_no_high_risk_contacts_is_reported_ok(self):
        t = _template("Hi", "<p>hi</p>", [])
        report = run_preflight(t, [_contact("a@example.com")], high_risk_emails=set())
        check = next(c for c in report.checks if c.id == "bounce_risk")
        assert check.severity == "ok"

    def test_high_risk_contacts_are_flagged_with_a_count(self):
        t = _template("Hi", "<p>hi</p>", [])
        report = run_preflight(
            t, [_contact("a@example.com"), _contact("b@example.com")],
            high_risk_emails={"b@example.com"},
        )
        check = next(c for c in report.checks if c.id == "bounce_risk")
        assert check.severity == "crit"
        assert "1" in check.title
        assert report.excluded_high_risk_count == 1


class TestDeliveryPrediction:
    def test_without_a_model_falls_back_to_a_stated_neutral_estimate(self):
        t = _template("Hi", "<p>hi</p>", [])
        report = run_preflight(t, [_contact("a@example.com")], bounce_probs=None)
        assert report.predicted_delivery == 95.0

    def test_with_model_output_averages_bounce_probability(self):
        t = _template("Hi", "<p>hi</p>", [])
        contacts = [_contact("a@example.com"), _contact("b@example.com")]
        report = run_preflight(t, contacts, bounce_probs=[0.1, 0.3])
        assert report.predicted_delivery == 80.0  # (1 - 0.2) * 100


class TestUndeclaredVariables:
    def test_a_template_with_a_body_var_not_in_its_own_declared_list_is_flagged(self):
        """Should never happen if validate_template ran at save time, but a
        template saved before that validation existed, or edited via a
        direct DB write, must still be caught here."""
        t = _template("Hi {{first_name}}", "<p>{{undeclared_var}}</p>", ["first_name"])
        report = run_preflight(t, [_contact("a@example.com")])
        undeclared_check = next((c for c in report.checks if c.id == "undeclared_variables"), None)
        assert undeclared_check is not None
        assert undeclared_check.severity == "crit"
