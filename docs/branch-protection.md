# Protecting `main`

`main` takes pull requests, not direct pushes.

This is enforced in two places, and only one of them is real.

| | Where | Enforces | Bypassable |
|---|---|---|---|
| Local hook | `scripts/git-hooks/pre-push` | Your machine | Yes — `--no-verify` |
| Branch protection | GitHub, repo settings | Everyone, always | No (except admins, if allowed) |

The hook catches the honest mistake. Branch protection is what actually holds.
Set up both.

## 1. The local hook (already in the repo)

Run once per clone:

```sh
./scripts/install-hooks.sh
```

This points `core.hooksPath` at `scripts/git-hooks/`, so a push to `main` is
refused with an explanation, and a push with a failing backend lint is refused
too.

Be clear about what this is not. It is a convenience, not a security control:

- Anyone can skip it with `git push --no-verify`.
- It does not exist for anyone who has not run the installer.
- It cannot stop a commit made through the GitHub web UI.

It exists because most direct-to-main pushes are a reflex — a `git push` while
`main` happened to be checked out — not a decision. It catches those.

## 2. Branch protection on GitHub (the one that counts)

**This requires admin on the repository.** At the time of writing the repo is
`manisha160505/HP-Acoount-Intelligence`, so the repo owner has to do this;
collaborators with `push` cannot, and the API returns a `404` rather than a
permission error if they try.

### Via the web UI

Settings → Branches → Add branch protection rule (or Settings → Rules → Rulesets
on newer repos).

Branch name pattern: `main`

Enable:

- **Require a pull request before merging** — the setting that closes direct pushes
  - Require approvals: 1 (or more)
  - Dismiss stale approvals when new commits are pushed
- **Require status checks to pass before merging** — add `Up to date with main`,
  `Backend lint`, `Backend tests` and `Frontend typecheck and build` (the job
  names in `.github/workflows/ci.yml`)
- **Require branches to be up to date before merging** — this is the setting
  that blocks a PR whose branch is missing commits from `main`. The CI job
  `Up to date with main` checks the same thing and prints which commits are
  missing, but its result goes stale when `main` moves after it ran; this
  setting does not
- **Do not allow bypassing the above settings** — otherwise admins silently keep the
  ability to push straight to `main`, which is usually not what people expect

Leave **Allow force pushes** and **Allow deletions** off.

### Via the CLI

Same thing, for an admin with a `repo`-scoped token:

```sh
gh api -X PUT repos/OWNER/REPO/branches/main/protection \
  --input - <<'JSON'
{
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true
  },
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Up to date with main",
      "Backend lint",
      "Backend tests",
      "Frontend typecheck and build"
    ]
  },
  "enforce_admins": true,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

`"strict": true` is "Require branches to be up to date before merging".
`enforce_admins: true` is what makes the rule apply to the owner too.

Verify it took:

```sh
gh api repos/OWNER/REPO/branches/main/protection --jq '{
  pr_required: (.required_pull_request_reviews != null),
  approvals: .required_pull_request_reviews.required_approving_review_count,
  up_to_date_required: .required_status_checks.strict,
  checks: .required_status_checks.contexts,
  admins_included: .enforce_admins.enabled,
  force_push: .allow_force_pushes.enabled
}'
```

## Everyday workflow

```sh
git switch -c feat/your-change
# ... work, commit ...
git push -u origin feat/your-change
gh pr create --base main
```

If you have already committed to `main` locally, the commits follow you onto a
new branch — nothing is lost:

```sh
git switch -c feat/your-change          # commits come along
git push -u origin feat/your-change
git branch -f main origin/main          # put local main back where it was
```
