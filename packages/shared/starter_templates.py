"""Starter templates seeded into every new organization at creation time.

Every declared variable below actually appears in the body (see
render.validate_template — an org member could otherwise hit "undeclared
variable" on a template they never touched), and `first_name` is always
declared since campaigns.py always supplies it at render time.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StarterTemplate:
    name: str
    subject: str
    html_body: str
    text_body: str | None
    variables: list[str]


STARTER_TEMPLATES: list[StarterTemplate] = [
    StarterTemplate(
        name="Announcement",
        subject="{{event_name}}: an update for you, {{first_name}}",
        html_body=(
            "<p>Hi {{first_name}},</p>"
            "<p>We wanted to share an update about {{event_name}}.</p>"
            "<p>{{message}}</p>"
            "<p>— The team</p>"
        ),
        text_body=(
            "Hi {{first_name}},\n\n"
            "We wanted to share an update about {{event_name}}.\n\n"
            "{{message}}\n\n— The team"
        ),
        variables=["first_name", "event_name", "message"],
    ),
    StarterTemplate(
        name="Event Outreach",
        subject="You're invited: {{event_name}}",
        html_body=(
            "<p>Hi {{first_name}},</p>"
            "<p>We'd love to have you at {{event_name}}.</p>"
            "<p>Your background in {{specialization}} is exactly what we're looking for.</p>"
            "<p><a href=\"{{event_link}}\">RSVP here</a></p>"
            "<p>— The team</p>"
        ),
        text_body=(
            "Hi {{first_name}},\n\n"
            "We'd love to have you at {{event_name}}.\n\n"
            "Your background in {{specialization}} is exactly what we're looking for.\n\n"
            "RSVP: {{event_link}}\n\n— The team"
        ),
        variables=["first_name", "event_name", "specialization", "event_link"],
    ),
    StarterTemplate(
        name="Follow-up",
        subject="Following up, {{first_name}}",
        html_body=(
            "<p>Hi {{first_name}},</p>"
            "<p>Just following up on {{event_name}} — {{message}}</p>"
            "<p>Let us know if you have any questions.</p>"
            "<p>— The team</p>"
        ),
        text_body=(
            "Hi {{first_name}},\n\n"
            "Just following up on {{event_name}} — {{message}}\n\n"
            "Let us know if you have any questions.\n\n— The team"
        ),
        variables=["first_name", "event_name", "message"],
    ),
]
