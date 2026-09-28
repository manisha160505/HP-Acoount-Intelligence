"""Which technology names in an export have been superseded inside that export.

The client, 27 Sep, on an Opportunity Map card built around Windows 7:

    "Are we sure we found Win 7 still in their fleet via their tech stack?
    Win 7 went into EOL Jan 2020, unlikely. I think this would have been
    Win 10, can we please double check on this."

We checked. The account's own Explorium export lists both, in one cell of
`Platform And Storage`:

    ... Microsoft SQL Server Integration Services, Microsoft Windows 7,
    Oracle Linux, Oracle Solaris, Tableau Software, ... VMware, Windows 10

So the card was reporting the file accurately and simply led with the older of
the two. The rule here reads nothing but the file: where one export names
several versions of the same product, the newest is the one worth a
recommendation and the older ones are not evidence of anything.

Deliberately NOT an end-of-life table. A support date is knowledge from outside
the account's files, it ages, and it would have to be maintained per product.
"Another version of this same product is in the same list" is a fact the
uploaded row itself states.
"""

import re

# A name ends in a version when its last token is a number: "Windows 10",
# "Microsoft Windows 7", "SQL Server 2019". A decimal counts ("Solaris 11.4");
# a year is just a large number and orders the same way.
_VERSION_TAIL = re.compile(r"^(?P<family>.*?)[\s\-]+v?(?P<version>\d+(?:\.\d+)*)$")

# Vendor prefixes that appear on one spelling of a product and not another.
# "Microsoft Windows 7" and "Windows 10" are the same family or this does
# nothing at all, which was the whole point.
_VENDOR_PREFIXES = ("microsoft ", "apple ", "oracle ", "google ", "adobe ",
                    "ibm ", "sap ", "red hat ", "vmware ", "hp ", "hewlett packard ")


# A trailing number is only a VERSION when it reads like one. Two shapes
# qualify and nothing else does:
#
#   a release number   - Windows 7, Windows 10, Solaris 11.4   (major < 100)
#   a release year     - SQL Server 2016, SQL Server 2019      (1990-2100)
#
# Everything else is a model or a brand and must be left alone. The first run
# of this rule marked "Microsoft Office 365" superseded by an Office release
# year, and six Cisco appliances superseded by their own siblings - Catalyst
# 6500 by Catalyst 6503. Those are not older versions of one another.
_MAX_RELEASE_NUMBER = 100
_YEAR_RANGE = (1990, 2100)


def _kind(major: int) -> str:
    """"v" for a release number, "y" for a release year, "" for neither.

    The two never compare: Windows 2000 is not a newer Windows 10.
    """
    if major < _MAX_RELEASE_NUMBER:
        return "v"
    if _YEAR_RANGE[0] <= major <= _YEAR_RANGE[1]:
        return "y"
    return ""


def _split(name: str):
    """(family, version tuple) for a versioned name, else None."""
    text = " ".join(str(name or "").split()).lower()
    match = _VERSION_TAIL.match(text)
    if not match:
        return None
    family = match.group("family").strip()
    for prefix in _VENDOR_PREFIXES:
        if family.startswith(prefix):
            family = family[len(prefix):].strip()
            break
    if not family:
        return None
    version = tuple(int(part) for part in match.group("version").split("."))
    kind = _kind(version[0])
    if not kind:
        return None
    return "%s|%s" % (family, kind), version


def spellings(name: str) -> tuple:
    """The ways a versioned product name is written, longest first.

    "Microsoft Windows 7" is what the export says; prose calls it "Windows 7".
    Searching for only the export's spelling missed the sentence that started
    this - "a mix of legacy systems (Windows 7) and newer systems (Windows
    10)" - even though the quote beneath it had already been corrected.
    """
    text = " ".join(str(name or "").split())
    split = _split(text)
    if not split:
        return (text.lower(),) if text else ()
    family, version = split
    short = "%s %s" % (family.split("|")[0],
                       ".".join(str(part) for part in version))
    out = [text.lower()]
    if short not in out:
        out.append(short)
    return tuple(out)


def superseded(names) -> set:
    """The names in `names` that a newer version of the same product outranks.

    Returns the ORIGINAL spellings, so a caller can match them against the cell
    they came from. A product named once, or named without a version, is never
    returned - this only ever fires when the export contradicts itself.
    """
    newest: dict = {}
    parsed: list = []
    for name in names or []:
        split = _split(name)
        if not split:
            continue
        family, version = split
        parsed.append((name, family, version))
        if version > newest.get(family, ()):
            newest[family] = version
    return {name for name, family, version in parsed if version < newest[family]}
