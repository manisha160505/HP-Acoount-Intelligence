"""The bulk onboarding pipeline - scripts/onboard_accounts.py.

Everything here runs without a network and without a database: the preflight
reader, the predicate that decides an account has finished, and the ledger that
makes a re-run resume rather than repeat.

The waiting predicate is the part worth pinning. "Wait until every node is
CURRENT" hangs forever on a real wave: a FAILED node sits out a 1h/6h/24h
backoff, a blocked one never retries until an input changes, and a node that is
merely queued reads STALE with a job attached rather than GENERATING.

Run: python -m pytest tests/test_onboarding.py -v
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import onboard_accounts as ob
import pytest

# --------------------------------------------------------------- preflight

def _write(folder, name, payload):
    path = folder / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _account(folder, name="A CO - PH"):
    _write(folder, "_account.json", {"name_for_upload": name})


def _manifest(folder, datasets, readiness=None):
    _write(folder, "_manifest.json",
           {"datasets": datasets, "readiness": readiness or {}})


REGISTRY = {"firmographics", "technographics", "prospect_contacts",
            "compliance_filings", "intent_score"}


@pytest.fixture
def folder(tmp_path):
    out = tmp_path / "A_CO"
    out.mkdir()
    return out


class TestTheUploadPlan:

    def test_a_dataset_with_rows_is_uploaded(self, folder):
        _account(folder)
        _manifest(folder, {"firmographics": {"rows": 1, "status": "ok"}})
        (folder / "firmographics.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        plan = ob.read_plan(folder, REGISTRY)
        assert plan.ok
        assert [k for k, _p, _r in plan.datasets] == ["firmographics"]

    def test_an_empty_dataset_is_skipped_not_uploaded(self, folder):
        """The split's own rule: "an empty registered dataset makes an
        extractor work from nothing, whereas an unregistered one degrades
        cleanly"."""
        _account(folder)
        _manifest(folder, {"firmographics": {"rows": 1, "status": "ok"},
                           "technographics": {"rows": 0, "status": "empty",
                                              "reason": "sheet is empty"}})
        (folder / "firmographics.csv").write_text("a\n1\n", encoding="utf-8")
        (folder / "technographics.csv").write_text("a\n", encoding="utf-8")
        plan = ob.read_plan(folder, REGISTRY)
        assert [k for k, _p, _r in plan.datasets] == ["firmographics"]
        assert plan.skipped == [("technographics", "sheet is empty")]

    def test_a_manifest_row_with_no_file_is_a_problem(self, folder):
        _account(folder)
        _manifest(folder, {"firmographics": {"rows": 12, "status": "ok"}})
        plan = ob.read_plan(folder, REGISTRY)
        assert not plan.ok
        assert "file is missing" in plan.problems[0]

    def test_a_zero_byte_file_is_a_problem(self, folder):
        """The upload endpoint answers 400 for it; better found here."""
        _account(folder)
        _manifest(folder, {"firmographics": {"rows": 3, "status": "ok"}})
        (folder / "firmographics.csv").write_text("", encoding="utf-8")
        plan = ob.read_plan(folder, REGISTRY)
        assert not plan.ok
        assert "0 bytes" in plan.problems[0]

    def test_a_key_the_api_does_not_accept_is_a_problem(self, folder):
        _account(folder)
        _manifest(folder, {"made_up_key": {"rows": 1, "status": "ok"}})
        plan = ob.read_plan(folder, REGISTRY)
        assert not plan.ok
        assert "not a dataset_key" in plan.problems[0]

    def test_filings_are_pdfs_on_disk_not_a_csv(self, folder):
        _account(folder)
        _manifest(folder, {"firmographics": {"rows": 1, "status": "ok"},
                           "compliance_filings": {"rows": 2, "status": "ok"}})
        (folder / "firmographics.csv").write_text("a\n1\n", encoding="utf-8")
        filings = folder / "compliance_filings"
        filings.mkdir()
        (filings / "one.pdf").write_bytes(b"%PDF-1.4")
        (filings / "_filings_index.csv").write_text("a\n", encoding="utf-8")
        plan = ob.read_plan(folder, REGISTRY)
        assert [p.name for p in plan.filings] == ["one.pdf"]
        assert "compliance_filings" not in [k for k, _p, _r in plan.datasets]

    def test_a_filings_row_with_no_pdf_is_skipped_not_failed(self, folder):
        _account(folder)
        _manifest(folder, {"firmographics": {"rows": 1, "status": "ok"},
                           "compliance_filings": {"rows": 4, "status": "ok"}})
        (folder / "firmographics.csv").write_text("a\n1\n", encoding="utf-8")
        (folder / "compliance_filings").mkdir()
        plan = ob.read_plan(folder, REGISTRY)
        assert plan.ok
        assert plan.filings == []
        assert plan.skipped[0][0] == "compliance_filings"

    def test_an_account_with_nothing_to_upload_is_a_problem(self, folder):
        _account(folder)
        _manifest(folder, {"firmographics": {"rows": 0, "status": "empty"}})
        plan = ob.read_plan(folder, REGISTRY)
        assert not plan.ok
        assert "nothing to upload" in plan.problems[0]

    def test_a_name_too_long_for_the_api_is_a_problem(self, folder):
        _account(folder, name="X" * 101)
        _manifest(folder, {"firmographics": {"rows": 1, "status": "ok"}})
        (folder / "firmographics.csv").write_text("a\n1\n", encoding="utf-8")
        plan = ob.read_plan(folder, REGISTRY)
        assert not plan.ok
        assert "100" in plan.problems[0]

    def test_an_unreadable_manifest_fails_the_account_not_the_wave(self, folder):
        _account(folder)
        (folder / "_manifest.json").write_text("{not json", encoding="utf-8")
        plan = ob.read_plan(folder, REGISTRY)
        assert not plan.ok
        assert "unreadable" in plan.problems[0]

    def test_the_missing_datasets_per_feature_are_reported(self, folder):
        _account(folder)
        _manifest(folder, {"firmographics": {"rows": 1, "status": "ok"}},
                  readiness={"executive_dashboard": {"status": "partial",
                                                     "missing": ["company_hierarchy"]},
                             "tech_landscape": {"status": "complete", "missing": []}})
        (folder / "firmographics.csv").write_text("a\n1\n", encoding="utf-8")
        plan = ob.read_plan(folder, REGISTRY)
        assert plan.features_missing_data() == [
            ("executive_dashboard", ["company_hierarchy"])]


class TestTheRegistryIsReadFromTheBackend:

    def test_the_keys_come_from_the_schema(self):
        """Parsed rather than imported: this script runs on a host that has no
        pydantic and no settings module."""
        repo = Path(__file__).resolve().parent.parent.parent
        keys = ob.dataset_registry_keys(repo)
        assert "firmographics" in keys
        assert "compliance_filings" in keys
        assert "company_personas" in keys        # added after the first wave
        assert "tech_breakdown" in keys
        assert len(keys) >= 25


# ------------------------------------------------------------- the waiter

def _node(lifecycle, job=None, blocked=False, blocked_by=None, quality=None,
          kind="producer"):
    return {"lifecycle": lifecycle, "job": job, "blocked": blocked,
            "blocked_by": blocked_by, "quality": quality, "kind": kind}


class TestWhenANodeHasStoppedMoving:

    def test_current_is_settled(self):
        assert ob.node_settled(_node(ob.CURRENT))

    def test_failed_is_settled(self):
        """Not success - but the retry backoff is an hour at best, so waiting
        on it is waiting forever."""
        assert ob.node_settled(_node(ob.FAILED))

    def test_generating_is_not_settled(self):
        assert not ob.node_settled(_node(ob.GENERATING))

    def test_a_queued_node_reads_stale_and_is_not_settled(self):
        """derive() reports GENERATING only for a RUNNING job, so a node that
        is merely queued looks STALE. Checking the lifecycle alone would call
        the account finished the moment it was queued."""
        entry = _node(ob.STALE, job={"id": "j1", "status": "PENDING"})
        assert not ob.node_settled(entry)

    def test_a_running_job_beats_a_current_lifecycle(self):
        entry = _node(ob.CURRENT, job={"id": "j1", "status": "RUNNING"})
        assert not ob.node_settled(entry)

    def test_never_generated_is_not_settled(self):
        assert not ob.node_settled(_node(ob.NEVER))

    def test_a_blocked_node_is_settled(self):
        """It will not retry until an input changes."""
        assert ob.node_settled(_node(ob.STALE, blocked=True))

    def test_a_node_waiting_on_a_stuck_ancestor_is_settled(self):
        assert ob.node_settled(_node(ob.STALE, blocked_by=["tech_core"]))

    def test_plain_stale_with_nothing_holding_it_is_not_settled(self):
        assert not ob.node_settled(_node(ob.STALE))


class TestTheOutcomeWord:

    def test_current_is_ok(self):
        assert ob.node_outcome(_node(ob.CURRENT)) == "ok"

    def test_degraded_is_reported_but_still_built(self):
        assert ob.node_outcome(_node(ob.CURRENT, quality="degraded")) == "degraded"

    def test_failed_is_failed(self):
        assert ob.node_outcome(_node(ob.FAILED)) == "failed"

    def test_blocked_is_blocked(self):
        assert ob.node_outcome(_node(ob.STALE, blocked_by=["news"])) == "blocked"


MIXED_NODES = {"exec_core": _node(ob.CURRENT),
               "idx_strategy": _node(ob.GENERATING, kind="index")}


class TestSkippingTheIndexes:

    def test_indexes_are_waited_on_by_default(self):
        assert set(ob.wanted_nodes(MIXED_NODES, skip_indexes=False)) == set(MIXED_NODES)

    def test_skip_indexes_leaves_only_the_producers(self):
        assert list(ob.wanted_nodes(MIXED_NODES, skip_indexes=True)) == ["exec_core"]


# -------------------------------------------------------------- the ledger

class TestTheLedger:

    def test_a_step_is_remembered_across_runs(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        first = ob.Ledger(path)
        assert not first.has("A_CO", "upload", "firmographics")
        first.add("A_CO", "upload", "firmographics", file_id="abc")

        second = ob.Ledger(path)
        assert second.has("A_CO", "upload", "firmographics")
        assert not second.has("A_CO", "upload", "technographics")

    def test_force_ignores_what_is_recorded(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ob.Ledger(path).add("A_CO", "filing", "q3.pdf")
        assert not ob.Ledger(path, force=True).has("A_CO", "filing", "q3.pdf")

    def test_a_corrupt_line_does_not_stop_the_resume(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ob.Ledger(path).add("A_CO", "upload", "firmographics")
        with path.open("a", encoding="utf-8") as handle:
            handle.write("{half written\n")
        assert ob.Ledger(path).has("A_CO", "upload", "firmographics")

    def test_filings_are_keyed_per_pdf(self, tmp_path):
        """compliance_filings is multi-file: a second POST of the same PDF adds
        a copy rather than replacing it, so each is remembered by name."""
        path = tmp_path / "ledger.jsonl"
        ledger = ob.Ledger(path)
        ledger.add("A_CO", "filing", "q3.pdf")
        assert ledger.has("A_CO", "filing", "q3.pdf")
        assert not ledger.has("A_CO", "filing", "q4.pdf")


# ------------------------------------------------------------- selection

class TestChoosingAccounts:

    @pytest.fixture
    def root(self, tmp_path):
        for name in ("B_CO", "A_CO", "_NOT_AN_ACCOUNT", "__MACOSX"):
            (tmp_path / name).mkdir()
        (tmp_path / "_ACCOUNTS.csv").write_text("x", encoding="utf-8")
        return tmp_path

    def test_folders_are_returned_sorted_and_index_files_skipped(self, root):
        assert ob.select_slugs(root, [], 0) == ["A_CO", "B_CO"]

    def test_a_named_account_is_selected(self, root):
        assert ob.select_slugs(root, ["B_CO"], 0) == ["B_CO"]

    def test_a_comma_separated_list_works(self, root):
        assert ob.select_slugs(root, ["A_CO,B_CO"], 0) == ["A_CO", "B_CO"]

    def test_a_limit_takes_the_first_n(self, root):
        assert ob.select_slugs(root, [], 1) == ["A_CO"]

    def test_an_unknown_account_stops_before_anything_is_sent(self, root):
        with pytest.raises(SystemExit):
            ob.select_slugs(root, ["NO_SUCH_CO"], 0)
