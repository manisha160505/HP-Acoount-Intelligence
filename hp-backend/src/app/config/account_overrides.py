"""Per-account display overrides, loaded from `config/account_overrides.yaml`.

The client decides, account by account, what not to show: a feature whose data
is not there (Intent with no Bombora topics and every HP category at 0, Tech
Landscape for a government account with no technology data), or a parent
company Explorium holds but nobody has confirmed. Those are decisions about one
account, so they live in a file anyone can edit rather than in a list in code.

## What hiding does, and what it does not

A hidden feature is removed from the account's sidebar, its widget API and the
Strategy Chat context. It is **still generated**: other features read its
sections (Live Signals scores against Intent and Tech Landscape, the HP
recommendations read Intent), and skipping them would break those instead.

## Validation is loud, at startup

An unknown field fails at import. Feature keys are checked against
`FEATURE_MAPPINGS` by `validate_feature_keys`, which `main.py` calls at startup
- not at import, because the feature map lives in the API package and importing
it from config would tie the two together. A typo here would otherwise show the
client exactly what they asked us to hide, with nothing logged.
"""

import logging
import os
import re

import yaml

logger = logging.getLogger(__name__)

_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.abspath(os.path.join(_CONFIG_DIR, "..", "..", ".."))
CONFIG_PATH = os.path.join(_BACKEND_ROOT, "config", "account_overrides.yaml")

_FIELDS = {"hidden_features", "hide_parent_company"}


class AccountOverridesError(RuntimeError):
    """Raised when the overrides file cannot be trusted. Deliberately fatal."""


def _key(name) -> str:
    """How a name is matched: case and runs of whitespace do not count."""
    return re.sub(r"\s+", " ", str(name or "")).strip().lower()


def _parse(config) -> dict:
    """{matched name: {"hidden_features": frozenset, "hide_parent_company": bool}}."""
    if not isinstance(config, dict):
        raise AccountOverridesError("account overrides: the file is not a mapping")
    accounts = config.get("accounts") or {}
    if not isinstance(accounts, dict):
        raise AccountOverridesError("account overrides: 'accounts' is not a mapping")
    out = {}
    for name, entry in accounts.items():
        entry = entry or {}
        if not isinstance(entry, dict):
            raise AccountOverridesError("account overrides: %r is not a mapping" % name)
        unknown = set(entry) - _FIELDS
        if unknown:
            raise AccountOverridesError("account overrides: %r has unknown field(s) %s"
                                        % (name, ", ".join(sorted(unknown))))
        hidden = entry.get("hidden_features") or []
        if not isinstance(hidden, list) or not all(isinstance(f, str) for f in hidden):
            raise AccountOverridesError(
                "account overrides: %r hidden_features must be a list of feature keys"
                % name)
        parent = entry.get("hide_parent_company", False)
        if not isinstance(parent, bool):
            raise AccountOverridesError(
                "account overrides: %r hide_parent_company must be true or false" % name)
        key = _key(name)
        if key in out:
            raise AccountOverridesError("account overrides: %r is listed twice" % name)
        out[key] = {"hidden_features": frozenset(f.strip().lower() for f in hidden),
                    "hide_parent_company": parent}
    return out


def _load() -> dict:
    if not os.path.exists(CONFIG_PATH):
        # No file is a valid state (a fresh checkout, a test): nothing is hidden.
        logger.info("account overrides: no %s - nothing hidden", CONFIG_PATH)
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        parsed = _parse(yaml.safe_load(handle) or {})
    logger.info("account overrides loaded: %d account(s) from %s",
                len(parsed), CONFIG_PATH)
    return parsed


OVERRIDES = _load()


def hidden_features(account_name) -> frozenset:
    """Feature keys hidden for this account; empty when none are."""
    return (OVERRIDES.get(_key(account_name)) or {}).get("hidden_features", frozenset())


def is_hidden(account_name, feature_key) -> bool:
    return str(feature_key or "").strip().lower() in hidden_features(account_name)


def hides_parent(account_name) -> bool:
    return bool((OVERRIDES.get(_key(account_name)) or {}).get("hide_parent_company"))


PARENT_WIDGET = "exec_summary_card"


def masked(account_name, widget_key: str, data: dict) -> dict:
    """The widget's data as this account may show it.

    Applied when a widget is read (dashboard and Strategy Chat), so editing the
    YAML takes effect at once - no regeneration of 220 Executive Dashboards. The
    extractor applies the same rule when it generates, so stored data agrees
    once it next runs. Returns a copy when anything is removed, never mutates.
    """
    if widget_key == PARENT_WIDGET and hides_parent(account_name) and (
            data.get("parent_company") or data.get("parent_company_source")
            or data.get("parent_companies")):
        # `parent_companies` is the list the card shows (an account can have
        # two parents); `parent_company` is the same names as one string.
        # `parent_companies_original` is the same names as supplied, for the
        # hover - hidden with them.
        return {**data, "parent_company": "", "parent_companies": [],
                "parent_company_source": None, "parent_companies_original": {}}
    return data


def validate_feature_keys(known) -> None:
    """Fail when a hidden feature is not a real feature key."""
    known = {str(k).lower() for k in known}
    for name, entry in OVERRIDES.items():
        bad = sorted(entry["hidden_features"] - known)
        if bad:
            raise AccountOverridesError(
                "account overrides: %r hides unknown feature(s) %s"
                % (name, ", ".join(bad)))
