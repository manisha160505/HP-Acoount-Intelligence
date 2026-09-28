# Engineering docs

The conventions this codebase actually enforces. Five documents, each about
code that is in the repository:

| Document | What it settles |
|---|---|
| [`api-envelope.md`](api-envelope.md) | The shape every `/api/v1` response comes back in, and what a client can rely on. |
| [`api-errors.md`](api-errors.md) | The error contract: codes, status mapping, and what a caller is told versus what is logged. |
| [`linting.md`](linting.md) | Ruff on `hp-backend`, what is enforced in CI, and how to run it locally. |
| [`observability.md`](observability.md) | Request ids, the log contract, the pipeline logging a supervised run reads, and the Cloud Logging queries. |
| [`branch-protection.md`](branch-protection.md) | Why `main` is protected, what the CI check does, and the local pre-push hook. |

## Everything else

The project's document library — client requirements, logic documents, decision
log, question trackers, data definitions, delivery planning — is **not in this
repository**. It lives under `project-documentation/` on the machines that need
it and is deliberately ignored by git: it is client material, it is large, and
none of it is required to build, test or run the application.

The two offline scripts that read from that folder
(`scripts/split_account_data.py`, `scripts/fetch_filings.py`) expect the
spreadsheets under
`project-documentation/04_Data_and_Source_Definitions/{Account_List,Filings}/`.
They read data files, never documents, and those data files are not committed
either.
