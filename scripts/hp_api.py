#!/usr/bin/env python3
"""One HTTP client for the scripts that talk to a running backend.

`split_account_data.py` grew these five helpers while it was the only script
uploading anything. `onboard_accounts.py` needs the same five, so they live
here rather than in either of them - one implementation of the envelope, the
multipart body and the login exchange, and one place to fix them.

Deliberately stdlib only. These scripts run on the VM, sometimes outside the
backend container, so `requests` is not available and importing the app would
drag in settings, Mongo and the whole dependency tree to send one POST.

Credentials come from the environment, never from an argument - an argument
lands in shell history:

    HP_TOKEN                 a bearer token from a browser session
    HP_EMAIL + HP_PASSWORD   a dashboard login, exchanged for a token here
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote


def unwrap(body):
    """The API wraps every response as {"success": true, "data": ...}.

    envelope_middleware does it for the whole v1 surface, so a caller that
    reads body["access_token"] gets None and reports a login failure on an
    HTTP 200.
    """
    if isinstance(body, dict) and "success" in body and "data" in body:
        return body["data"]
    return body


def api(url: str, token: str = "", payload=None, method: str = "",
        timeout: int = 600):
    """(status, unwrapped body). An HTTP error is a status, not an exception."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method or ("POST" if data is not None else "GET"))
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer %s" % token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, (unwrap(json.loads(body)) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            return exc.code, unwrap(json.loads(body))
        except ValueError:
            return exc.code, {"detail": body[:400]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # A refused connection or a read timeout is the same kind of answer as
        # a 500 to every caller here: this request did not land.
        return 0, {"detail": repr(exc)[:400]}


def api_upload(url: str, token: str, dataset_key: str, path: Path,
               defer: bool = True, timeout: int = 900):
    """One multipart POST of one file, written out by hand.

    `defer` asks the endpoint to store the file without re-running the features
    that declare it. A feature with seven dependencies would otherwise run
    seven times per account, six of them against a half-loaded account; the
    caller regenerates each feature once when every dataset is in.
    """
    boundary = "----hpapi" + datetime.now(UTC).strftime("%H%M%S%f")
    sep = ("--%s" % boundary).encode()
    body = b"".join([
        sep, b"\r\n",
        b'Content-Disposition: form-data; name="dataset_key"\r\n\r\n',
        dataset_key.encode(), b"\r\n",
        sep, b"\r\n",
        b'Content-Disposition: form-data; name="defer_extraction"\r\n\r\n',
        (b"true" if defer else b"false"), b"\r\n",
        sep, b"\r\n",
        ('Content-Disposition: form-data; name="file"; filename="%s"\r\n'
         % path.name).encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        path.read_bytes(), b"\r\n",
        sep, b"--\r\n",
    ])
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=%s" % boundary)
    if token:
        req.add_header("Authorization", "Bearer %s" % token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode()
            return resp.status, (unwrap(json.loads(text)) if text else None)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode(errors="replace")
        try:
            return exc.code, unwrap(json.loads(text))
        except ValueError:
            return exc.code, {"detail": text[:400]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"detail": repr(exc)[:400]}


def token_expiry(token: str):
    """Seconds left on a JWT, or None when it carries no readable exp.

    Read locally, without the signing secret: the claims are base64 and only
    the signature needs the secret. A wave runs longer than the 24h token, so
    a caller can renew before a 401 rather than after one.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload)).get("exp")
        return None if exp is None else exp - time.time()
    except (IndexError, ValueError, TypeError):
        return None


def login(base_url: str, email: str, password: str) -> str:
    status, body = api("%s/api/v1/auth/login" % base_url,
                       payload={"email": email, "password": password})
    if status != 200 or not body or "access_token" not in body:
        sys.exit("login failed (HTTP %s)" % status)
    return body["access_token"]


def api_token(base_url: str) -> str:
    token = (os.getenv("HP_TOKEN") or "").strip()
    if token:
        return token
    email, password = os.getenv("HP_EMAIL"), os.getenv("HP_PASSWORD")
    if not email or not password:
        sys.exit("set HP_TOKEN, or HP_EMAIL and HP_PASSWORD, in the environment")
    return login(base_url, email, password)


def renewed(base_url: str, token: str, min_seconds: int = 1800) -> str:
    """The same token, or a fresh one when it is close to expiring.

    Only possible with HP_EMAIL/HP_PASSWORD - a token pasted into HP_TOKEN
    cannot be renewed, so it is returned as it is and the caller gets a 401
    when it lapses. There is no refresh endpoint.
    """
    left = token_expiry(token)
    if left is None or left > min_seconds:
        return token
    email, password = os.getenv("HP_EMAIL"), os.getenv("HP_PASSWORD")
    if not (email and password):
        return token
    return login(base_url, email, password)


def find_or_create_account(base_url: str, token: str, name: str,
                           dry_run: bool = False):
    """(account_id, "existing" | "created" | "would create"), or raises.

    Find first: a repeat create is a 400, not an idempotent 200, and the
    uniqueness check is application-level with no unique index behind it - so
    callers must serialise creation rather than race it.
    """
    status, body = api("%s/api/v1/accounts?search=%s" % (base_url, quote(name)),
                       token)
    if status == 200 and isinstance(body, list):
        for row in body:
            if (row.get("name") or "").strip().lower() == name.strip().lower():
                return row["id"], "existing"
    if dry_run:
        return "", "would create"
    status, body = api("%s/api/v1/accounts" % base_url, token, {"name": name})
    if status not in (200, 201) or not body:
        detail = (body or {}).get("detail") or body
        raise RuntimeError("could not create account %r (HTTP %s): %s"
                           % (name, status, detail))
    return body["id"], "created"
