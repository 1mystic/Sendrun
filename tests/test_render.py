"""The render pipeline in isolation — no DB, no HTTP. These are the tests that
matter most for Phase 2: the sandbox actually sandboxes, personalization
happens before sanitization (so a hostile contact field cannot inject HTML),
and a missing variable is reported rather than silently blanked without a
trace.
"""

from __future__ import annotations

import pytest
from jinja2.exceptions import SecurityError

from packages.shared.render import (
    TemplateValidationError,
    check_link,
    extract_links,
    extract_used_variables,
    render_for_contact,
    sanitize,
    validate_template,
)


class TestValidateTemplate:
    def test_accepts_a_well_formed_template(self):
        validate_template(
            "Hi {{first_name}}", "<p>Hello {{first_name}}, join {{event_name}}</p>",
            None, ["first_name", "event_name"],
        )  # must not raise

    def test_rejects_a_variable_used_but_not_declared(self):
        with pytest.raises(TemplateValidationError, match="undeclared"):
            validate_template("Hi {{first_name}}", "<p>{{secret_field}}</p>", None, ["first_name"])

    def test_rejects_invalid_jinja_syntax(self):
        with pytest.raises(TemplateValidationError, match="invalid syntax"):
            validate_template("Hi {{first_name", "<p>ok</p>", None, ["first_name"])

    def test_extract_used_variables_finds_all_three_bodies(self):
        used = extract_used_variables("{{a}}", "<p>{{b}}</p>", "{{c}} and {{a}}")
        assert used == {"a", "b", "c"}


class TestSandboxEscape:
    """The sandbox's entire job is refusing the classic escape patterns. If any
    of these render successfully, the sandbox has a hole."""

    def test_cannot_reach_class_attribute_chain(self):
        validate_template("x", "{{ ''.__class__ }}", None, [])
        with pytest.raises(SecurityError):
            render_for_contact(
                subject="x", html_body="{{ ''.__class__.__mro__[1].__subclasses__() }}",
                text_body=None, declared_variables=[], contact_fields={},
            )

    def test_cannot_call_import(self):
        with pytest.raises(SecurityError):
            render_for_contact(
                subject="x", html_body="{{ self.__init__.__globals__ }}",
                text_body=None, declared_variables=[], contact_fields={},
            )

    def test_only_declared_variables_are_bound(self):
        """A contact's `fields` dict may hold arbitrary extra keys the template
        never asked for — none of them should be reachable."""
        rendered = render_for_contact(
            subject="Hi", html_body="<p>{{first_name}}</p>", text_body=None,
            declared_variables=["first_name"],
            contact_fields={"first_name": "Rahul", "internal_notes": "flagged for fraud review"},
        )
        assert "flagged" not in rendered.html_body
        assert "Rahul" in rendered.html_body


class TestPersonalizationOrder:
    """Contact data is untrusted input (CLAUDE.md invariant 8). A hostile value
    must come out of the OUTPUT clean, whether it looks like markup or script."""

    def test_html_in_a_contact_field_is_neutralized(self):
        rendered = render_for_contact(
            subject="Hi", html_body="<p>Hello {{first_name}}</p>", text_body=None,
            declared_variables=["first_name"],
            contact_fields={"first_name": "<script>alert(1)</script>"},
        )
        assert "<script" not in rendered.html_body
        assert "alert(1)" not in rendered.html_body or "&lt;script&gt;" in rendered.html_body

    def test_a_contact_field_cannot_inject_a_new_tag(self):
        """Autoescape HTML-entity-encodes the substituted value before bleach
        ever runs, so the literal text 'onerror' can legitimately survive as
        inert escaped content (&lt;img ... onerror=... &gt;) — what matters is
        that no LIVE <img> element or attribute exists in the output."""
        rendered = render_for_contact(
            subject="Hi", html_body="<p>{{first_name}}</p>", text_body=None,
            declared_variables=["first_name"],
            contact_fields={"first_name": '<img src=x onerror=alert(1)>'},
        )
        assert "<img" not in rendered.html_body
        assert "&lt;img" in rendered.html_body  # present only as escaped text


class TestMissingVariables:
    def test_missing_variable_is_reported_not_silently_blank(self):
        rendered = render_for_contact(
            subject="Hi {{first_name}}", html_body="<p>Re: {{specialization}}</p>", text_body=None,
            declared_variables=["first_name", "specialization"],
            contact_fields={"first_name": "Arjun"},
        )
        assert rendered.missing_variables == ("specialization",)
        assert rendered.is_complete is False

    def test_complete_contact_has_no_missing_variables(self):
        rendered = render_for_contact(
            subject="Hi {{first_name}}", html_body="<p>{{first_name}}</p>", text_body=None,
            declared_variables=["first_name"], contact_fields={"first_name": "Arjun"},
        )
        assert rendered.is_complete is True

    def test_fallback_is_used_for_a_missing_variable(self):
        rendered = render_for_contact(
            subject="Hi", html_body="<p>Re: {{specialization}}</p>", text_body=None,
            declared_variables=["specialization"], contact_fields={},
            fallback="your work",
        )
        assert "your work" in rendered.html_body


class TestSanitize:
    def test_strips_script_tags(self):
        assert "<script" not in sanitize("<p>hi</p><script>evil()</script>")

    def test_strips_event_handler_attributes(self):
        assert "onclick" not in sanitize('<a href="#" onclick="evil()">click</a>')

    def test_keeps_ordinary_markup(self):
        out = sanitize("<p>Hello <b>world</b></p>")
        assert "<b>world</b>" in out

    def test_strips_iframe(self):
        assert "<iframe" not in sanitize('<iframe src="evil.com"></iframe>')


class TestLinks:
    def test_extracts_hrefs(self):
        links = extract_links('<a href="https://example.com">x</a> <a href="mailto:a@b.com">y</a>')
        assert links == ["https://example.com", "mailto:a@b.com"]

    def test_rejects_javascript_scheme(self):
        assert check_link("javascript:alert(1)").ok is False

    def test_accepts_https(self):
        assert check_link("https://sendrun.app/x").ok is True

    def test_rejects_malformed_url(self):
        assert check_link("http://").ok is False
