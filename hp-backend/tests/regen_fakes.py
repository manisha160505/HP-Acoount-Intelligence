"""An in-memory stand-in for the slice of pymongo the regeneration engine uses.

The engine's guarantees rest on Mongo semantics - partial unique indexes,
atomic `find_one_and_update`, `$max`/`$min`/`$setOnInsert` on upsert - so this
fake implements those faithfully rather than approximately, including raising
`DuplicateKeyError` when a write would violate a unique index. Every engine
test also runs against a real mongod when `REGEN_TEST_MONGO_URI` is set, which
is what keeps this fake honest.

Every operation holds one lock, so concurrent-worker tests see the same
per-operation atomicity a server gives.
"""

import copy
import re
import threading
from datetime import UTC, datetime

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

_MISSING = object()


def _get(doc, path):
    node = doc
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return _MISSING
    return node


def _set(doc, path, value):
    parts = path.split(".")
    node = doc
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def _unset(doc, path):
    parts = path.split(".")
    node = doc
    for part in parts[:-1]:
        node = node.get(part)
        if not isinstance(node, dict):
            return
    node.pop(parts[-1], None)


def _norm(v):
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=UTC)
    return v


def _cmp_ok(actual, op, expected):
    if actual is _MISSING or actual is None:
        return False
    actual, expected = _norm(actual), _norm(expected)
    try:
        return {"$lt": actual < expected, "$lte": actual <= expected,
                "$gt": actual > expected, "$gte": actual >= expected}[op]
    except TypeError:
        return False


def _eq(actual, expected):
    if expected is None:
        return actual is _MISSING or actual is None
    if isinstance(actual, list) and not isinstance(expected, list):
        return any(_norm(a) == _norm(expected) for a in actual)
    return actual is not _MISSING and _norm(actual) == _norm(expected)


def matches(doc, query) -> bool:
    for key, cond in (query or {}).items():
        if key == "$or":
            if not any(matches(doc, q) for q in cond):
                return False
            continue
        if key == "$and":
            if not all(matches(doc, q) for q in cond):
                return False
            continue
        actual = _get(doc, key)
        if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
            for op, val in cond.items():
                if op == "$in":
                    if not any(_eq(actual, v) for v in val):
                        return False
                elif op == "$nin":
                    if any(_eq(actual, v) for v in val):
                        return False
                elif op == "$ne":
                    if _eq(actual, val):
                        return False
                elif op == "$size":
                    if not isinstance(actual, list) or len(actual) != val:
                        return False
                elif op == "$exists":
                    if (actual is not _MISSING) != bool(val):
                        return False
                elif op == "$regex":
                    if actual is _MISSING or not re.search(val, str(actual or "")):
                        return False
                elif op in ("$lt", "$lte", "$gt", "$gte"):
                    if not _cmp_ok(actual, op, val):
                        return False
                else:
                    raise NotImplementedError(op)
        elif not _eq(actual, cond):
            return False
    return True


def _apply(doc, update, inserting):
    for op, fields in update.items():
        for path, value in fields.items():
            current = _get(doc, path)
            if op == "$set":
                _set(doc, path, copy.deepcopy(value))
            elif op == "$setOnInsert":
                if inserting:
                    _set(doc, path, copy.deepcopy(value))
            elif op == "$unset":
                _unset(doc, path)
            elif op == "$inc":
                _set(doc, path, (0 if current is _MISSING else current) + value)
            elif op == "$push":
                items = value["$each"] if isinstance(value, dict) and "$each" in value \
                    else [value]
                base = [] if current is _MISSING or current is None else list(current)
                _set(doc, path, base + copy.deepcopy(items))
            elif op == "$addToSet":
                base = [] if current is _MISSING or current is None else list(current)
                items = value["$each"] if isinstance(value, dict) and "$each" in value \
                    else [value]
                for item in items:
                    if item not in base:
                        base.append(copy.deepcopy(item))
                _set(doc, path, base)
            elif op == "$pull":
                base = [] if current is _MISSING or current is None else list(current)
                _set(doc, path, [v for v in base if v != value])
            elif op == "$max":
                if current is _MISSING or current is None or _norm(value) > _norm(current):
                    _set(doc, path, value)
            elif op == "$min":
                if current is _MISSING or current is None or _norm(value) < _norm(current):
                    _set(doc, path, value)
            else:
                raise NotImplementedError(op)


def _check_conflicting_paths(update):
    seen = set()
    for fields in update.values():
        for path in fields:
            if path in seen:
                raise ValueError("Updating the path '%s' would create a conflict" % path)
            seen.add(path)


class _Result:
    def __init__(self, matched=0, modified=0, upserted_id=None, deleted=0,
                 inserted_id=None):
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = upserted_id
        self.inserted_id = inserted_id
        self.deleted_count = deleted


class FakeCursor(list):
    def sort(self, key, direction=None):
        keys = key if isinstance(key, list) else [(key, direction or 1)]
        for field, d in reversed(keys):
            super().sort(key=lambda x: _sort_key(_get(x, field)), reverse=d < 0)
        return self

    def limit(self, n):
        return FakeCursor(self[:n]) if n else self

    def skip(self, n):
        return FakeCursor(self[n:])


def _sort_key(v):
    if v is _MISSING or v is None:
        return (0, "")
    v = _norm(v)
    if isinstance(v, bool):
        return (1, int(v))
    if isinstance(v, int | float):
        return (1, v)
    if isinstance(v, datetime):
        return (2, v.timestamp())
    return (3, str(v))


class FakeCollection:
    def __init__(self, name, lock):
        self.name = name
        self.docs = []
        self.indexes = {}
        self._lock = lock

    def with_options(self, **_kw):
        return self

    # -- indexes ----------------------------------------------------------
    def create_index(self, keys, name=None, unique=False, partialFilterExpression=None,
                     **_options):
        with self._lock:
            fields = [k for k, _ in keys]
            name = name or "_".join("%s_1" % f for f in fields)
            spec = {"fields": fields, "unique": unique,
                    "partial": partialFilterExpression or {}}
            existing = self.indexes.get(name)
            if existing and existing != spec:
                raise ValueError("index %s exists with different options" % name)
            for other_name, other in self.indexes.items():
                if other_name != name and other["fields"] == fields and \
                        other["partial"] == spec["partial"]:
                    raise ValueError("equivalent index already exists")
            self.indexes[name] = spec
            self._check(self.docs)
            return name

    def _check(self, docs):
        ids = [d["_id"] for d in docs]
        if len(ids) != len(set(map(str, ids))):
            raise DuplicateKeyError("E11000 duplicate key _id",
                                    details={"keyValue": {"_id": ids[-1]}})
        for name, spec in self.indexes.items():
            if not spec["unique"]:
                continue
            seen = {}
            for d in docs:
                if spec["partial"] and not matches(d, spec["partial"]):
                    continue
                key = tuple(repr(_get(d, f)) for f in spec["fields"])
                if key in seen:
                    raise DuplicateKeyError(
                        "E11000 duplicate key error index: %s" % name,
                        details={"keyValue": {f: _get(d, f) for f in spec["fields"]},
                                 "index": name})
                seen[key] = True

    # -- reads ------------------------------------------------------------
    def _find(self, query):
        return [d for d in self.docs if matches(d, query)]

    def find(self, query=None, projection=None):
        with self._lock:
            return FakeCursor(copy.deepcopy(d) for d in self._find(query or {}))

    def find_one(self, query=None, projection=None, sort=None):
        rows = self.find(query or {})
        if sort:
            rows = rows.sort(sort)
        return rows[0] if rows else None

    def count_documents(self, query):
        with self._lock:
            return len(self._find(query))

    def distinct(self, field, query=None):
        with self._lock:
            out = []
            for d in self._find(query or {}):
                v = _get(d, field)
                if v is not _MISSING and v not in out:
                    out.append(v)
            return out

    def aggregate(self, pipeline):
        with self._lock:
            rows = copy.deepcopy(self.docs)
        for stage in pipeline:
            (op, spec), = stage.items()
            if op == "$group":
                groups = {}
                for r in rows:
                    gid = {k: _get(r, v.lstrip("$")) for k, v in spec["_id"].items()}
                    key = repr(gid)
                    g = groups.setdefault(key, {"_id": gid})
                    for out_field, acc in spec.items():
                        if out_field != "_id":
                            g[out_field] = g.get(out_field, 0) + acc["$sum"]
                rows = list(groups.values())
            elif op == "$match":
                rows = [r for r in rows if matches(r, spec)]
            elif op == "$limit":
                rows = rows[:spec]
            else:
                raise NotImplementedError(op)
        return iter(rows)

    # -- writes -----------------------------------------------------------
    def insert_one(self, doc):
        with self._lock:
            doc = copy.deepcopy(doc)
            doc.setdefault("_id", ObjectId())
            self._check([*self.docs, doc])
            self.docs.append(doc)
            return _Result(inserted_id=doc["_id"])

    def insert_many(self, docs, ordered=True):
        with self._lock:
            docs = [copy.deepcopy(d) for d in docs]
            for d in docs:
                d.setdefault("_id", ObjectId())
            self._check([*self.docs, *docs])
            self.docs.extend(docs)
            return _Result()

    def _write(self, query, update, upsert, sort=None, many=False):
        _check_conflicting_paths(update)
        positions = [i for i, d in enumerate(self.docs) if matches(d, query)]
        if sort:
            keys = sort if isinstance(sort, list) else [(sort, 1)]
            for field, d in reversed(keys):
                positions.sort(key=lambda i, f=field: _sort_key(_get(self.docs[i], f)),
                               reverse=d < 0)
        if not many:
            positions = positions[:1]
        if positions:
            before = [copy.deepcopy(self.docs[i]) for i in positions]
            trial = copy.deepcopy(self.docs)
            for i in positions:
                _apply(trial[i], update, inserting=False)
            self._check(trial)
            self.docs[:] = trial
            return before, [copy.deepcopy(self.docs[i]) for i in positions], None
        if not upsert:
            return [], [], None
        doc = {}
        for key, cond in query.items():
            if key.startswith("$") or (isinstance(cond, dict) and cond and
                                       all(k.startswith("$") for k in cond)):
                continue
            _set(doc, key, copy.deepcopy(cond))
        _apply(doc, update, inserting=True)
        doc.setdefault("_id", ObjectId())
        self._check([*self.docs, doc])
        self.docs.append(doc)
        return [], [copy.deepcopy(doc)], doc["_id"]

    def update_one(self, query, update, upsert=False):
        with self._lock:
            before, _after, upserted = self._write(query, update, upsert)
            return _Result(matched=len(before), modified=len(before), upserted_id=upserted)

    def update_many(self, query, update, upsert=False):
        with self._lock:
            before, _after, upserted = self._write(query, update, upsert, many=True)
            return _Result(matched=len(before), modified=len(before), upserted_id=upserted)

    def find_one_and_update(self, query, update, projection=None, sort=None,
                            upsert=False, return_document=False):
        with self._lock:
            before, after, _up = self._write(query, update, upsert, sort=sort)
            if return_document:          # ReturnDocument.AFTER is True
                return after[0] if after else None
            return before[0] if before else None

    def delete_many(self, query):
        with self._lock:
            keep = [d for d in self.docs if not matches(d, query)]
            n = len(self.docs) - len(keep)
            self.docs[:] = keep
            return _Result(deleted=n)


class FakeDb:
    def __init__(self):
        self._lock = threading.RLock()
        self._cols = {}

    def __getitem__(self, name):
        with self._lock:
            if name not in self._cols:
                self._cols[name] = FakeCollection(name, self._lock)
            return self._cols[name]
