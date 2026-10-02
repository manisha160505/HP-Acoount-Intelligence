# HP VM commands

Everything below runs **on the VM, from `~/hp`**. Nothing here calls a model or
changes data unless the section says so.

```bash
gcloud compute ssh hp-app-vm --zone asia-south1-c     # from your laptop
cd ~/hp
alias dc='docker compose -f docker-compose.prod.yml'  # shortcut used below
```

`dc` only lasts for this session. To keep it, add the alias line to `~/.bashrc`.

---

## 1. Are my latest changes deployed?

**The one-line answer:** compare what is running with GitHub `main`.
```bash
git fetch -q origin && echo "running: $(cat ~/.hp-deploy/deployed_sha | cut -c1-8)   github main: $(git rev-parse origin/main | cut -c1-8)   failed: $(cat ~/.hp-deploy/failed_sha 2>/dev/null | cut -c1-8)"
```
- If `running` equals `github main`, the deploy is done.
- If they differ, the deploy is waiting for CI or still in progress. Autodeploy checks every 2 minutes.
- If `failed` equals `github main`, CI failed or the deploy rolled back. See the log below.

**Which commits are running:**
```bash
git log -3 --oneline
```

**What autodeploy did:**
```bash
journalctl -u hp-autodeploy --since "6 hours ago" --no-pager | grep -E "deploying|deployed|waiting for CI|FAILED|rolled back|CI failed"
```
```bash
systemctl list-timers hp-autodeploy.timer --no-pager      # when it checks next
```

**The containers were rebuilt** (check the CREATED column):
```bash
dc ps
```

**The app is healthy:**
```bash
dc exec backend python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
```

**Is a specific change inside the running code?** The code lives in `/app/src/app` in the container.
```bash
dc exec backend grep -n "EMBEDDING_TIMEOUT" src/app/services/retrieval/client.py      # PR #43
dc exec backend grep -c "BUILD_GRAPH" src/app/services/retrieval/client.py            # PR #42, graph off
dc exec backend ls src/app/services/strategy/context.py                                # PR #41, whole-account chat
```

**What the running app actually loaded:**
```bash
dc exec -w /app/src backend python -c "
from app.services.retrieval import client, registry
from app.services.regen.graph import DEFAULT
print('graph build      :', client.BUILD_GRAPH)
print('exec mode        :', registry.spec('executive_dashboard')['default_mode'])
print('embed timeout    :', getattr(client, 'EMBEDDING_TIMEOUT', 'NOT DEPLOYED'), '(LightRAG cutoff = x2 seconds)')
print('index nodes      :', [n for n in DEFAULT.nodes if DEFAULT[n].kind == 'index'])"
```

**Settings in use** (no secrets are printed):
```bash
dc exec -w /app/src backend python -c "
from app.config.settings import settings as s
print('provider:', s.llm_provider, '| chat:', s.chat_model, '| embed:', s.embedding_model, '| region:', s.VERTEX_EMBEDDING_LOCATION, '| thinking:', s.GEMINI_THINKING_BUDGET)"
```

---

## 2. Logs

```bash
dc logs backend -f --since 10m                                   # live
dc logs backend --since 1h 2>&1 | grep -E '"level": "(ERROR|WARNING)"' | tail -30
dc logs backend --since 3h 2>&1 | grep -E "429|RESOURCE_EXHAUSTED|quota|Worker.*timeout" | tail -30   # rate limits
dc logs backend --since 3h 2>&1 | grep -E "regen\.(failed|done|cancelled)" | tail -30                # pipeline outcomes
dc logs backend --since 3h 2>&1 | grep "app.observability.pipeline" | tail -40                        # step-by-step progress
```

---

## 3. Pipelines (regeneration)

Set the account once. Find its id by name first if you need to:
```bash
dc exec -w /app/src backend python -c "
from app.database.mongodb import get_db
for a in get_db().accounts.find({'name': {'\$regex': 'ADVANTEST', '\$options': 'i'}}, {'name': 1}): print(a['_id'], a['name'])"
```
```bash
ACCT=6ab7ef16dc090e37050c56dd     # Advantest - change as needed
```

**What is running, queued or failed right now** (all accounts):
```bash
dc exec -w /app/src backend python -c "
from app.database.mongodb import get_db
db = get_db()
for j in db.regen_jobs.find({'status': {'\$in': ['RUNNING', 'PENDING']}}):
    p = j.get('progress') or {}
    print(j['status'], '|', j['account_id'], '|', j['node_id'], '|', p.get('label', ''), p.get('done', ''), '/', p.get('total', ''))
print('queue paused:', (db.regen_control.find_one({'_id': 'queue'}) or {}).get('paused', False))"
```

**The last 10 failures, with the reason:**
```bash
dc exec -w /app/src backend python -c "
from app.database.mongodb import get_db
for j in get_db().regen_jobs.find({'status': 'FAILED'}).sort('finished_at', -1).limit(10):
    e = j.get('error') or {}
    print(j.get('finished_at'), '|', j['account_id'], '|', j['node_id'], '|', e.get('code'), '-', str(e.get('message', ''))[:150])"
```

**One account: every section's last generation and last failure:**
```bash
dc exec -w /app/src backend python -c "
from app.database.mongodb import get_db
for s in get_db().node_state.find({'account_id': '$ACCT'}).sort('node_id', 1):
    f = s.get('last_failure') or {}
    print(s['node_id'].ljust(28), 'generated:', (s.get('current') or {}).get('generated_at'), '| running:', bool(s.get('running')), '| last failure:', f.get('code', '-'), str(f.get('message', ''))[:90])"
```

**One account: the Executive Dashboard index state:**
```bash
dc exec -w /app/src backend python -c "
from app.database.mongodb import get_db
s = get_db().retrieval_index_state.find_one({'account_id': '$ACCT', 'index': 'executive_dashboard'}) or {}
print('status:', s.get('status'), '| documents:', len(s.get('documents') or {}), '| built:', s.get('last_built_at'))
print('error :', str(s.get('last_error'))[:400])"
```

**The last 5 runs (Submit clicks), with their outcome:**
```bash
dc exec -w /app/src backend python -c "
from app.database.mongodb import get_db
for r in get_db().regen_runs.find().sort('created_at', -1).limit(5):
    print(r.get('created_at'), '|', r.get('status'), '|', r.get('account_ids'), '|', r.get('_id'))"
```

To run a pipeline, use **Admin → account → Pipeline tab → Preview → Submit** (not Force).

---

## 4. Uploaded files for an account

```bash
dc exec -w /app/src backend python -c "
from app.database.mongodb import get_db
for f in get_db().account_data_files.find({'account_id': '$ACCT', 'status': 'active'}).sort('dataset_key', 1):
    print(f['dataset_key'].ljust(24), f.get('uploaded_at'), f.get('original_filename'))"
```

Check that the files are really on disk:
```bash
ls -la hp-backend/data/accounts/$ACCT/
ls -la hp-backend/data/accounts/$ACCT/compliance_filings/
```

---

## 5. Actions that change something

| What | Command | Effect |
|---|---|---|
| Restart the backend | `dc restart backend` | Anything running ends as **Failed: INTERRUPTED**. Submit again to resume from saved progress. |
| Rebuild after a manual `.env` edit | `dc up -d backend` | Picks up the new `.env` |
| Deploy or roll back to a commit by hand | `deploy/deploy.sh <40-char sha>` | Same as autodeploy. Rolls back if the new commit is unhealthy. |
| Stop autodeploy | `sudo systemctl disable --now hp-autodeploy.timer` | Merges no longer deploy. Undo with `enable --now`. |

---

## 6. VM health

```bash
df -h /                          # disk space
free -h                          # memory
docker stats --no-stream         # CPU and memory per container
du -sh hp-backend/data hp-backend/rag_storage     # uploads and vectors
```
