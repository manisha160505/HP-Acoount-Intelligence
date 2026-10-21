"""Reading one contact's Stakeholder Map talking points, safely.

Talking points are stored keyed by contact_id, and each entry records the full
name of the person it was written for. An id can come to name someone else
after a contacts reload, so a reader joining on contact_id alone could show one
person's opener on another person's card. The Stakeholder Map prunes such
entries when it writes (`stakeholder_map.talking_points_for_current_contacts`); every
reader applies the same rule again here, so an entry kept by an older
generation is never attached to the wrong person.
"""


def _name_key(value) -> str:
    """A name as it is compared: case and runs of whitespace do not count."""
    return " ".join(str(value or "").split()).lower()


def for_contact(talking_points, contact_id, full_name) -> dict:
    """The talking-point entry for this contact, or {}.

    {} when there is none, when it is not a mapping, or when it records a
    `full_name` that is not this contact's (case- and space-insensitive). An
    entry with no recorded name is returned as it is.
    """
    if not isinstance(talking_points, dict):
        return {}
    entry = talking_points.get(str(contact_id or "").strip())
    if not isinstance(entry, dict):
        return {}
    stored = entry.get("full_name")
    if isinstance(stored, str) and stored.strip() and \
            _name_key(stored) != _name_key(full_name):
        return {}
    return entry
