# HP 220 Account Intelligence: User Management & Sessions, Tech Design

16 Oct 2026 · Yogesh · Live copy: https://claude.ai/code/artifact/87d9534f-ec98-44d0-9dea-bf9015cbf7d0

## Summary

We will give each HP user access only to their own accounts. We will also replace today's 24-hour token, which is stored in the browser, with a server-side session in a secure cookie. The session ends after 8 hours of inactivity, so a user who comes back after 2–3 hours is still signed in.

- **What changes for users:** a seller signs in and sees only the accounts the client assigned to them, as EAM or IAM in *Bridge AI users FY26 SNA*. Any other account shows "No access". Admins see every account.
- **Roles now:** Admin and User. Super Admin is on hold, as the client asked.
- **Sessions:** a random session id sits in an HttpOnly cookie, and the server checks it against a `sessions` collection on every request. A session can be revoked at once: on sign-out, "sign out of all devices", a password change or deactivation.
- **Before any HP user is invited:** fix four security gaps found in the code. The most urgent: every backend start re-creates default logins with passwords anyone with the code knows.
- **Initial users:** a script loads 7 admins and 100 sellers across 219 accounts from the client's workbook.
- **Delivery:**
  - Phase 0: security.
  - Phase 1: sessions, account access, user admin, the user import.
  - Phase 2: invite and reset emails, which need an email provider.

## Primer: the concepts behind the design

**Authentication answers "who are you?"; authorization answers "what may you see or do?"**
- Signing in with email and password is authentication.
- Deciding that Priya may open Astra but not Maybank is authorization.
- Today the platform authenticates users but authorizes only by role (admin or user), so every user can open every account.

**A JWT (JSON Web Token)** is a small signed note the server hands out at sign-in, for example `{sub: <user id>, role: user, exp: <expiry time>}`.
- The server signs it with a secret key. Later it can check that the note wasn't changed, without storing anything.
- The cost of that convenience: a JWT stays valid until its `exp`. The server can't cancel one early unless it keeps a list of cancelled tokens, and keeping that list removes the "stores nothing" benefit.

**A cookie** is a value the browser stores for one site and sends back automatically on every request to that site. Three flags matter:

| Flag | What it does | Why we want it |
| --- | --- | --- |
| HttpOnly | Page JavaScript cannot read the cookie | A script injected into the page (XSS) cannot steal the session |
| Secure | Sent only over HTTPS | Never travels in clear text |
| SameSite=Lax | Not sent on requests started by other websites (except plain link clicks) | Blocks most cross-site request forgery (CSRF) |

**The real choice is where the credential lives, not "JWT vs cookie".** A cookie can carry a JWT or a random session id, and a JWT can sit in a cookie or in localStorage.

| | localStorage + Bearer header (today) | HttpOnly cookie |
| --- | --- | --- |
| Readable by page scripts | Yes: any XSS can copy it | No |
| Sent automatically | No: code adds the header; links need `?token=` in the URL | Yes, including PDF links and downloads |
| CSRF exposure | None | Needs SameSite plus a header check |
| Works across domains | Yes | Best on one origin, which we have (Caddy serves app and API together) |

## How sign-in works today

Sign-in issues one JWT that lasts 24 hours, kept in the browser's localStorage. Nothing refreshes it, nothing can revoke it early, and any user can open any account.

- **Login:** `POST /api/v1/auth/login` checks a bcrypt password hash in the `users` collection and returns a JWT (`hp-backend/src/app/services/auth.py:178`).
- **Token:** PyJWT, HS256, with only the claims `sub`, `role` and `exp`.
  - There's no refresh token and no revocation list (`core/security.py:16`).
  - The backend re-reads the user on every request, so a deactivated user is refused at once (`core/deps.py:37`).
- **Browser:** the token sits in localStorage (`hp-frontend/src/providers/AuthProvider.tsx:21`), and axios sends it as a Bearer header (`services/api.ts:14`).
  - Filing PDFs, dataset downloads and the page-close event put it in the URL as `?token=` (`dashboard/page.tsx:412`, `:1010`; `lib/track.ts:166`).
- **Roles:** `admin` or `user`. Admins can create users (always role `user`, with a temporary password), list them, and deactivate or reactivate them (`api/v1/admin_users.py`).
- **Account access:** there is none.
  - `GET /accounts/user-list` returns every active account to every user.
  - About 22 account routes only check that the account exists (`api/v1/widgets.py`, `account_data.py`, `regeneration.py`). These include widgets, Strategy Chat, filings, downloads and regeneration status.
  - The dashboard hides other accounts in the UI, but nothing stops a direct request.
- **Email:** the backend cannot send email yet.

### Is the JWT hardcoded?

No. Every sign-in creates a new JWT for that user, signed with a secret key, and it expires on its own. Two settings around it do live in the code, and those are most likely what "hardcoded" refers to:

- **The signing secret has a fallback written in the code** (`settings.py:31`). If a server's env file doesn't set `JWT_SECRET`, tokens are signed with a value anyone with the code knows, so tokens could be forged. This is a security fix, not the cause of sign-outs.
- **The expiry has a default in code:** 1440 minutes, or 24 hours (`settings.py:37`). It's a fixed lifetime counted from sign-in, with no refresh and no inactivity rule.

### Why local and server sign-in times differ

The expiry setting is `ACCESS_TOKEN_EXPIRE_MINUTES`. The code default is 1440 minutes (24 h), in `hp-backend/src/app/config/settings.py:37`.
- **Any `.env` file overrides it.** Both local `.env` files set their own value, and the VM reads its own file, `deploy/.env.prod`. So each machine silently uses whatever its own file says.
- **The live server uses the default.** A token from the live server today expires **24.0 hours** after sign-in. A raised local value affects only your laptop.
- **The design below fixes this:**
  - timeouts become committed defaults in the code;
  - the per-machine override is removed;
  - the admin Platform page shows the live values.

**Can the expiry simply be raised or lowered?** Yes. Set `ACCESS_TOKEN_EXPIRE_MINUTES` in the server's `deploy/.env.prod` and restart the backend; the new value applies to tokens issued after the restart. That's a 5-minute stopgap, with two limits:

- **The server is already at 24 hours,** longer than the 2–3 hours asked for. A user signed out sooner than that is hitting something other than the expiry, and that needs its own look: when did it happen, in which browser, and was it right after a deploy?
- **A longer fixed token has two weaknesses:**
  - It can't be cancelled early, and the longer it lives in localStorage, the longer a stolen copy keeps working.
  - It can't sign out an idle user.

**What is safe to keep until the new sessions ship:**

| Setting | Keep | Why |
| --- | --- | --- |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 480–1440 (8–24 h); not above 1440 | Covers a working day; longer only widens the window for a stolen token |
| `JWT_SECRET` | A random 64-character value, set on the server, never in git | Without it tokens can be forged |
| Local `.env` | Remove the expiry line, so local runs use the code default like the server | Ends the silent local-vs-server difference |
| Default logins | Change both passwords on the live site now | They are written in the code |

### Security gaps to close before HP users are invited

| # | Gap | Where | Fix |
| --- | --- | --- | --- |
| 1 | Every backend start creates `admin@hp.com` and `user@hp.com` with known passwords if missing. Both work on the live site today. | `database/seed.py:7`, `core/seeder.py:40` | Remove startup seeding; create the first admin only with `scripts/seed_admin.py`; change the existing passwords |
| 2 | `JWT_SECRET` falls back to a value written in the code; the production example leaves it blank | `config/settings.py:31`, `deploy/env.prod.example:31` | Refuse to start without a strong secret |
| 3 | CORS allows any origin with credentials; the `CORS_ORIGINS` setting is never read | `main.py:143` | Allow only the site's own origin |
| 4 | The token travels in URLs, so it lands in server logs and browser history | see Browser above | Removed by the cookie session |

## Sessions: a server-side session in an HttpOnly cookie

We replace the localStorage JWT with a random session id in an HttpOnly cookie, backed by a `sessions` record that the server checks on every request.
- Users stay signed in while they're active.
- They're signed out after 8 hours with no activity.
- They can be signed out instantly.

**How it works**

1. **Sign-in:** the backend checks the password, creates a `sessions` record and sets the cookie `hp_session` (HttpOnly, Secure, SameSite=Lax, Path=/). The response body carries the user, not a token.
2. **Every request:**
   - the backend reads the cookie and loads the session;
   - it rejects the session if it was revoked, has been idle more than 8 hours, or is older than the absolute limit;
   - it then loads the user, still checking `is_active`.
3. **Activity extends the session:** `last_seen_at` is updated at most once a minute, so the 8-hour idle window keeps sliding forward at almost no cost.
4. **Sign-out** revokes the session and clears the cookie. "Sign out of all devices" (A8), a password change and deactivation revoke every session of that user.

**The `sessions` collection** has these fields:
- `_id` (a 32-byte random id, stored hashed), `user_id`, `ip`, `user_agent`;
- `created_at`, `last_seen_at`, `idle_expires_at`, `absolute_expires_at`, `revoked_at`.

A Mongo TTL index deletes expired records.

**Timeouts: one place, the same on every machine**

| Setting | Default | Meaning |
| --- | --- | --- |
| `SESSION_IDLE_MINUTES` | 480 (8 h) | Signed out after this long with no activity (client Q6, F5). A user back after 2–3 h is still signed in |
| `SESSION_MAX_HOURS` | 168 (7 days) | Must sign in again at least once a week, however active |

The defaults live in `settings.py` and are committed to git. The `.env` files stop setting them, so every machine runs the same values, and the admin Platform page shows the live values.

**What else changes**

- **Frontend:**
  - `AuthProvider` stops storing a token. On load it calls `GET /auth/me`: a 200 means signed in, a 401 sends the user to `/login`.
  - axios sends `withCredentials` and an `X-Requested-With` header.
- **Links:** filing PDFs and downloads drop `?token=`; the cookie goes with them automatically. `sendBeacon` sends the cookie too.
- **CSRF:** SameSite=Lax, plus the backend refuses any POST, PATCH or DELETE without the `X-Requested-With` header, which other websites cannot add.
- **Scripts:** `split_account_data.py` and other tools keep working through personal API tokens. Only admins can create them, and each has an expiry and can be revoked.
- **Local development:** Next.js forwards `/api` to the backend on port 8000. The app and API then share one origin in development, as they do on the server.
- **Rollout:** for one release, Bearer tokens are accepted alongside cookies; after that they're switched off.

## Roles and account access

A user sees only the accounts granted to them. One backend check guards every account route, so a direct link to another account returns "No access", never data. Admins see every account.

**Roles**

| Role | Can do | Notes |
| --- | --- | --- |
| Admin | All accounts; manage users and their accounts; create other Admins (D4); audit log; existing admin pages | Cannot deactivate or demote themselves (D6) |
| User | Only granted accounts; own name and password | |
| Super Admin | On hold (client) | The `role` field accepts `super_admin` later without a data change |

**Data model**

- **`account_grants`:**
  - Fields: `user_id` (or `email` before the user exists), `account_id`, `granted_by`, `granted_at`, `source` (`client_list`, `admin` or `upload`).
  - Unique on user + account.
  - Indexed both ways, for "a user's accounts" (C1–C3) and "who can see this account" (C4, C5).
- **`users.all_accounts: bool`** is for a user who should see every account, including ones added later (C6).
- **`users.internal: bool`** marks BridgeAI staff (see the client's blue questions below).

**Enforcement**

- **One FastAPI dependency, `require_account_access(account_id, user)`:**
  - It loads the account and lets admins and `all_accounts` users through.
  - Anyone else needs a grant, or gets **403 "No access"**.
  - It replaces the account lookup that each handler repeats today.
- **It's applied to every account route a user can reach:**
  - in `widgets.py`: widgets and regenerate, Message Evaluator, Strategy Chat (including the streaming ask), and retrieval status;
  - in `account_data.py`: filings and their PDFs, downloads, and unreachable links;
  - in `regeneration.py`: feature regenerate, status and jobs.
- **Two list endpoints filter instead of refusing:** `GET /accounts/user-list` returns only granted accounts, and `POST /events` drops events for accounts the user cannot see.
- **A unit test lists every route with `{account_id}`** and fails if one lacks the dependency, so a new route can't skip the check.
- **Frontend:** the account picker shows only the user's accounts, and a 403 shows a "No access" page instead of the dashboard.
- **Changes take effect on the next request (C3),** because grants are read live, not stored in the session.

## User lifecycle, emails and audit

Admins create users by invite link or temporary password, and every change is recorded in an audit log. The email parts need an email provider, which we don't have yet.

**User lifecycle (the rows the client marked Yes)**

| Capability | Rows | How |
| --- | --- | --- |
| Create a user with email, name, role, accounts | B1, B3 | Admin Users page; temporary password sets `must_change_password` |
| Invite by email | B2, B11, F1 | One-time link valid 72 h (token stored hashed); resend creates a new one |
| Must set a new password at first sign-in | A5 | Sign-in with `must_change_password` goes straight to a set-password screen |
| Change own password | A3 | Needs the current password; revokes the user's other sessions; emails the user (F2) |
| Forgot password | A4, B10 | Reset link valid 1 h, same reply whether or not the email exists |
| Edit own name | A6 | Profile page (admins do not edit names, B6 = No) |
| List and search users | B4, B5 | Role, accounts, status, last sign-in; search by email |
| Deactivate, reactivate, delete | B7–B9, Q9 | Deactivate keeps history and revokes sessions; delete removes the user and their grants, audit entries stay |
| Email when accounts are added | F3 | One email per change listing the new accounts |

**Password rules:** minimum 12 characters (Q5), hashed with bcrypt as today. There's no lockout (F4 = No). Instead, sign-in is rate-limited per IP address, which slows password guessing without locking anyone out.

**Emails need two things we don't have yet:**
- an email service: an SMTP account (for example the company's mail server), SendGrid, or Amazon SES;
- a sender address, such as `no-reply@<domain>`.

Until one is chosen, Phase 1 ships with temporary passwords only.

**Audit and activity**

- **`audit_log`** records who did what, to which user or account, the before and after values, and when. It covers every user, role and access change (E1), with an admin page and filters.
- **Last sign-in per user** already exists as `last_login_at` (E2).
- **Which accounts each user viewed and when (E3)** comes from the existing `usage_events` (kept 365 days), shown per user on the admin pages.
- **CSV export** of users with their accounts (E4).

## Loading the client's user list

A script loads *Bridge AI users FY26 SNA*: 7 admins, and 100 sellers with grants on 219 accounts. Three account names need mapping, and one platform account has no users.

- **Admin tab:** the 7 `@hp.com` emails become Admins, with all accounts.
- **Sales tab:** each row is one account (column C) with an EAM (column D) and an IAM (column E).
  - Each email becomes a User, granted that account.
  - That gives 100 distinct users, with one email per cell; no admin is also a seller.
- **Running it:**
  - A dry run first prints every user, role and account, plus any name that doesn't match.
  - The script can be re-run safely: it adds only what's missing, and records `source = client_list` in the audit log.
  - Invites or temporary passwords go out on a date agreed with the client.

**Names that differ between the sheet and the platform**

| Client sheet | Platform account | Proposed |
| --- | --- | --- |
| BUNNINGS GROUP LIMITED- AU | BUNNINGS GROUP LIMITED | Same account (missing space and country) |
| INDONESIA FINANCIAL GROUP - ID | INDONESIA FINANCIAL GROUP - CATEGORY1 - PARTIAL - ID | Same account |
| TIARA MARGA TRAKINDO - ID | PT TIARA MARGA TRAKINDO - CATEGORY1 - PARTIAL - ID | Same account |
| (not in sheet) | AUSTRALIAN SUBMARINE CORPORATION [ASC] - AU | Admins only until the client names its users |

## Phasing, tests and answers to the client's questions

The work comes in three phases, with a fourth group the client deferred. No HP user is invited until Phase 0 and Phase 1 are live and tested.

1. **Phase 0, security:**
   - stop seeding default logins at startup, and change their passwords;
   - require `JWT_SECRET`;
   - allow only the site's own origin in CORS;
   - remove the expiry line from local `.env` files.
2. **Phase 1, access:**
   - cookie sessions with an 8 h idle timeout and a 7-day limit;
   - `account_grants`, with `require_account_access` on every account route;
   - the admin Users page: roles, accounts, search, deactivate, delete, temporary passwords, CSV export;
   - own password and name;
   - the audit log;
   - loading the client list (dry run, then live).
3. **Phase 2, email:** invite links and forgot-password, password-changed and accounts-added emails, once an email service is chosen.
4. **Later (client's choice):**
   - Super Admin (D1–D3, D5) and periodic password change;
   - bulk upload of users (B12);
   - access that expires (C9), and access to some sections only (C10);
   - two-step verification (F6) and single sign-on (F7);
   - parent/child access (Q10, pending Sahaj).

**Tests**

- **Backend unit tests:**
  - every `{account_id}` route has the access check;
  - a user gets 403 on another account and 200 on their own;
  - idle and absolute expiry work;
  - sessions are revoked on sign-out, password change and deactivation;
  - a request without the CSRF header is refused.
- **Import:** a dry run against the workbook reports 7 admins, 100 users, 219 grants and the four names above.
- **End to end on the server:**
  - sign in as a test seller and see only their accounts;
  - open another account's link and get "No access";
  - leave the tab idle past the timeout and get signed out.

**Answers to the client's blue questions**

| Question | Our answer |
| --- | --- |
| A new account is added with user emails: can those users get it automatically? | Yes. Grants can be stored by email, before or after the user exists. When an account is uploaded with its EAM/IAM emails, or an admin lists emails on it, those users see it on their next page load. |
| Q3: should the client's Admins see and manage BridgeAI's internal admins? | We suggest hiding them: BridgeAI staff are marked internal, left out of the client's user lists and activity reports, and cannot be changed by client Admins. BridgeAI keeps its own admin accounts for support. |

## Open decisions

- [ ] Session choice: server-side session in a cookie (recommended) vs a JWT in a cookie with refresh, or a longer JWT as today
- [ ] Absolute session limit: 7 days?
- [ ] Email service and sender address for invites and resets (Phase 2)
- [ ] Client: hide BridgeAI internal admins from their Admins (Q3)?
- [ ] Client: confirm the three name mappings and who should see ASC
- [ ] Client: parent/child access rule (Q10, pending Sahaj)
- [ ] Date to send invites or temporary passwords to the 107 HP users
