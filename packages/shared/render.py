"""The template render pipeline: resolve -> validate -> personalize -> sanitize -> validate links.

Order matters. Personalization happens BEFORE sanitization, because a contact's
own field values are untrusted input (CLAUDE.md invariant 8) — a contact named
`<script>alert(1)</script>` must have that neutralized in the OUTPUT, and
sanitizing only the template author's markup would miss it entirely.

Contact data is never treated as instructions. This module only ever
substitutes it into a `{{var}}` slot and then strips anything dangerous out of
the result — it never reaches an LLM prompt or a code path that branches on
its content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import bleach
from jinja2 import StrictUndefined
from jinja2.exceptions import TemplateSyntaxError, UndefinedError
from jinja2.sandbox import ImmutableSandboxedEnvironment

# ─────────────────────────────────────────────────────────────────────────────
# The sandboxed environment
# ─────────────────────────────────────────────────────────────────────────────

# ImmutableSandboxedEnvironment (not the plain SandboxedEnvironment) additionally
# forbids mutating any object reachable from the template, closing off the
# classic Jinja2 sandbox-escape pattern of calling a mutator method on a passed-in
# object. autoescape=True HTML-escapes every substitution by default; sanitize()
# below is a second, independent layer for the parts of the body that are meant
# to already be HTML (the template author's own markup).
_env = ImmutableSandboxedEnvironment(autoescape=True, undefined=StrictUndefined)

# StrictUndefined makes referencing an undeclared variable raise instead of
# silently rendering empty string — a missing {{event_name}} must be visible in
# the preflight report, not swallowed into blank space in a sent email.

VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

# Deliberately small. This is marketing/transactional email copy, not a general
# document — there is no reason a contact template needs <script>, <iframe>,
# <object>, or event-handler attributes, so none of bleach's defaults for those
# are extended.
ALLOWED_TAGS = [
    "a", "b", "strong", "i", "em", "u", "p", "br", "hr",
    "ul", "ol", "li", "blockquote", "code", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td",
    "img", "span", "div",
]
ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "width", "height"],
    # No "style": allowing it without a css_sanitizer means bleach passes raw
    # CSS through unchecked (and warns on every call). Email clients strip most
    # inline CSS anyway; if inline styling is needed later, add a real
    # css_sanitizer rather than re-allowing this attribute bare.
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────

class TemplateValidationError(Exception):
    """Raised at template-save time (not send time) for problems the author must
    fix before the template can be used at all — bad Jinja2 syntax, or a
    `{{var}}` used in the body that was never declared in `variables`."""


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: declared-variable validation (template-save time)
# ─────────────────────────────────────────────────────────────────────────────

def extract_used_variables(subject: str, html_body: str, text_body: str | None) -> set[str]:
    """Every `{{name}}` actually referenced in the template text."""
    used: set[str] = set()
    for text in (subject, html_body, text_body or ""):
        used.update(VAR_PATTERN.findall(text))
    return used


def validate_template(
    subject: str, html_body: str, text_body: str | None, declared: list[str]
) -> None:
    """Called when a template is saved, not when it is sent.

    Two checks: the Jinja2 syntax must parse, and every `{{var}}` used in the
    body must appear in the author's own `declared` list. This is an allowlist,
    not free-form Jinja2 — an author cannot reference an arbitrary attribute path
    like `{{contact.__class__}}` because nothing except the declared plain names
    is ever bound into the render context (see render_for_contact below).
    """
    used = extract_used_variables(subject, html_body, text_body)
    undeclared = used - set(declared)
    if undeclared:
        raise TemplateValidationError(
            f"template uses undeclared variable(s): {', '.join(sorted(undeclared))}. "
            f"Add them to the template's variable list before saving."
        )

    bodies = (("subject", subject), ("html_body", html_body), ("text_body", text_body or ""))
    for label, text in bodies:
        try:
            _env.parse(text)
        except TemplateSyntaxError as exc:
            raise TemplateValidationError(f"invalid syntax in {label}: {exc.message}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: render for one contact (send time / preview time)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class LinkCheck:
    url: str
    ok: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    html_body: str
    text_body: str | None
    missing_variables: tuple[str, ...] = ()
    links: tuple[LinkCheck, ...] = field(default=())

    @property
    def is_complete(self) -> bool:
        """False if any declared variable had no value for this contact — the
        signal a preflight check uses to flag "N recipients missing X"."""
        return len(self.missing_variables) == 0


def sanitize(html: str) -> str:
    """The second, independent layer. Autoescape in the Jinja2 env protects
    substituted VALUES; this protects the template author's own MARKUP — a
    template body is written by an org member, but it is still safer to strip
    scripts/handlers than to trust every editor forever."""
    return bleach.clean(
        html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, protocols=ALLOWED_PROTOCOLS, strip=True
    )


def _resolve_context(
    declared: list[str], fields: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    """Only declared variables are ever bound into the render context — a
    contact's `fields` dict may carry arbitrary extra keys (freeform per-contact
    data), and none of them leak into the template unless explicitly declared.
    Missing ones are tracked, not defaulted, so the caller can report them."""
    context: dict[str, str] = {}
    missing: list[str] = []
    for name in declared:
        value = fields.get(name)
        if value is None or value == "":
            missing.append(name)
        else:
            context[name] = value
    return context, missing


def render_for_contact(
    *,
    subject: str,
    html_body: str,
    text_body: str | None,
    declared_variables: list[str],
    contact_fields: dict[str, str],
    fallback: str = "",
    check_links: bool = True,
) -> RenderedEmail:
    """Render one template for one contact.

    A missing variable does not raise — it renders as `fallback` (empty by
    default) so preview and send both produce a complete email, and the caller
    decides from `missing_variables` whether that recipient should be excluded.
    Raising here would make a single incomplete contact abort an entire batch
    render, which is far more disruptive than surfacing the gap.
    """
    context, missing = _resolve_context(declared_variables, contact_fields)
    for name in missing:
        context[name] = fallback

    try:
        rendered_subject = _env.from_string(subject).render(**context)
        rendered_html = _env.from_string(html_body).render(**context)
        rendered_text = _env.from_string(text_body).render(**context) if text_body else None
    except UndefinedError as exc:
        # Only reachable if the template references a variable outside `declared`
        # that slipped past validate_template (e.g. a template saved before this
        # pipeline existed). Fail loudly rather than send a broken email.
        raise TemplateValidationError(f"template references an unbound variable: {exc}") from exc

    clean_html = sanitize(rendered_html)
    links = tuple(check_link(u) for u in extract_links(clean_html)) if check_links else ()

    return RenderedEmail(
        subject=rendered_subject,
        html_body=clean_html,
        text_body=rendered_text,
        missing_variables=tuple(missing),
        links=links,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Link extraction / validation (offline shape-check; live HTTP check is a
# separate, explicitly-invoked preflight step — never run implicitly on every
# render, since that would make every "preview as recipient" click do network I/O)
# ─────────────────────────────────────────────────────────────────────────────

_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


def extract_links(html: str) -> list[str]:
    return _HREF_RE.findall(html)


def check_link(url: str) -> LinkCheck:
    """Static shape validation only — scheme allowlist and a well-formed host.
    Does not make a network request; see docs/AI_SPEC.md for the live-fetch
    preflight check, which is opt-in and rate-limited."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https", "mailto"):
        return LinkCheck(url, ok=False, reason=f"unsupported scheme: {parsed.scheme or '(none)'}")
    if parsed.scheme in ("http", "https") and not parsed.netloc:
        return LinkCheck(url, ok=False, reason="missing host")
    return LinkCheck(url, ok=True)
