import json
import hashlib
from pathlib import Path
import shutil
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import loop_engineering.cli as cli_module

CLI = Path(__file__).resolve().parents[1] / "loop_engineering" / "cli.py"


def run_cli(*args):
    return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def bind_artifact(record):
    record = dict(record)
    record.pop("content_hash", None)
    payload = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    record["content_hash"] = hashlib.sha256(
        payload.encode("utf-8")).hexdigest()
    return record


def execution(command="python -m unittest", exit_code=0):
    return {
        "command": command,
        "exit_code": exit_code,
        "executed_at": "2026-11-15T10:00:00+08:00",
    }


def rebind_record_hashes(records):
    artifacts = [
        record for record in records.values()
        if record.get("kind") == "artifact"
    ]
    for artifact in artifacts:
        artifact["content_hash"] = bind_artifact(artifact)["content_hash"]
    by_version = {
        artifact["version"]: artifact["content_hash"]
        for artifact in artifacts
    }
    artifacts_by_version = {
        artifact["version"]: artifact for artifact in artifacts
    }
    for record in records.values():
        if record.get("kind") in {"verification", "approval"}:
            record["artifact_content_hash"] = by_version.get(
                record.get("artifact_version"))
    for record in records.values():
        if record.get("kind") == "decision":
            record["artifact_hashes"] = {
                version: by_version[version]
                for version in record.get("artifact_versions", [])
                if version in by_version
            }
            if (record.get("decision") == "ACCEPT"
                    and len(record.get("artifact_versions", [])) == 1):
                version = record["artifact_versions"][0]
                if version in artifacts_by_version:
                    record["reviewed_set_digest"] = (
                        cli_module.reviewed_set_sha256(
                            list(records.values()),
                            artifacts_by_version[version]))
    return records


def stage2_records():
    artifact = {
        "schema_version": 3,
        "id": "A-1",
        "kind": "artifact",
        "artifact_type": "test",
        "content": "candidate",
        "source": "test",
        "work_item_id": "WI-1",
        "files": ["result.txt", "notes.txt"],
        "producer_context": {
            "session_id": "producer-session",
            "model": "producer-model",
            "authentication": "unverified_host_attestation",
        },
    }
    records = {
        "work-item.json": {
            "schema_version": 3,
            "id": "WI-1",
            "kind": "work_item",
            "goal": "resolve records",
            "pack_id": "software-development",
            "constraints": [],
            "priority": "medium",
            "risk_level": "medium",
            "control_tier": "L2",
            "route_flags": {
                "trivial": False,
                "ambiguous": False,
                "irreversible": False,
            },
            "max_repair_iterations": 3,
            "acceptance_criteria": {"AC-1": "result is verified"},
            "open_questions": [],
        },
        "artifact-1.json": bind_artifact(dict(artifact, version="1")),
        "artifact-2.json": bind_artifact(dict(artifact, version="2")),
        "verification.json": {
            "schema_version": 3,
            "id": "V-1",
            "kind": "verification",
            "artifact_id": "A-1",
            "artifact_version": "2",
            "artifact_content_hash": bind_artifact(
                dict(artifact, version="2"))["content_hash"],
            "criterion_ids": ["AC-1"],
            "check": "result",
            "method": "python -m unittest",
            "status": "PASS",
            "evidence": ["command exited 0"],
            "limitations": [],
            "role": "verifier",
            "execution": execution(),
        },
        "decision.json": {
            "schema_version": 3,
            "id": "D-1",
            "kind": "decision",
            "cycle": 2,
            "work_item_id": "WI-1",
            "artifact_versions": ["2"],
            "artifact_hashes": {
                "2": bind_artifact(dict(artifact, version="2"))[
                    "content_hash"],
            },
            "decision": "ACCEPT",
            "rationale": "verified",
            "evidence_refs": ["V-1", "V-REVIEW"],
            "unresolved_disagreements": [],
            "approver": "controller",
            "criteria_evidence": {
                "AC-1": {"verification_ids": ["V-1"], "result": "PASS"}
            },
            "residual_risks": [],
            "review_independence": "independent",
        },
        "verification-review.json": {
            "schema_version": 3,
            "id": "V-REVIEW",
            "kind": "verification",
            "artifact_id": "A-1",
            "artifact_version": "2",
            "artifact_content_hash": bind_artifact(
                dict(artifact, version="2"))["content_hash"],
            "criterion_ids": ["AC-1"],
            "role": "reviewer",
            "execution": execution("host-session: reviewer"),
            "host_context": {
                "session_id": "reviewer-session",
                "model": "reviewer-model",
                "independence": "independent",
                "authentication": "unverified_host_attestation",
            },
            "check": "independent review",
            "method": "review artifact",
            "status": "PASS",
            "evidence": ["review completed"],
            "limitations": [],
        },
        "verification-repair-evidence.json": {
            "schema_version": 3,
            "id": "V-REPAIR-EVIDENCE",
            "kind": "verification",
            "artifact_id": "A-1",
            "artifact_version": "1",
            "artifact_content_hash": bind_artifact(
                dict(artifact, version="1"))["content_hash"],
            "criterion_ids": ["AC-1"],
            "role": "verifier",
            "check": "repair finding",
            "method": "inspect version 1",
            "status": "PASS",
            "evidence": ["finding reproduced on version 1"],
            "limitations": [],
            "execution": execution("python -m unittest repair"),
        },
        "decision-repair.json": {
            "schema_version": 3,
            "id": "D-REPAIR",
            "kind": "decision",
            "cycle": 1,
            "work_item_id": "WI-1",
            "artifact_versions": ["1"],
            "artifact_hashes": {
                "1": bind_artifact(dict(artifact, version="1"))[
                    "content_hash"],
            },
            "decision": "REPAIR",
            "rationale": "produce the next version",
            "evidence_refs": ["V-REPAIR-EVIDENCE"],
            "unresolved_disagreements": [],
            "approver": "controller",
            "next_state": "PRODUCE",
            "repair_kind": "artifact",
        },
        "iterations/iteration-01.json": {
            "schema_version": 3,
            "id": "I-1",
            "kind": "iteration",
            "work_item_id": "WI-1",
            "cycle": 1,
            "input_versions": ["1"],
            "output_versions": ["2"],
            "changes": ["produced version 2"],
            "result": "REPAIR",
        },
    }
    return rebind_record_hashes(records)


def legacy_v2_records():
    return {
        "work-item.json": {
            "schema_version": 2,
            "id": "WI-OLD",
            "kind": "work_item",
            "goal": "migrate old records",
            "pack_id": "software-development",
            "constraints": [],
            "priority": "medium",
            "risk_level": "medium",
            "max_repair_iterations": 3,
            "acceptance_criteria": {"AC-1": "works"},
            "open_questions": [],
        },
        "artifact.json": {
            "schema_version": 2,
            "id": "A-1",
            "kind": "artifact",
            "artifact_type": "test",
            "version": "1",
            "content": "candidate",
            "source": "legacy",
            "files": ["one.py", "two.py"],
            "work_item_id": "WI-OLD",
        },
        "verification.json": {
            "schema_version": 2,
            "id": "V-1",
            "kind": "verification",
            "artifact_id": "A-1",
            "artifact_version": "1",
            "criterion_ids": ["AC-1"],
            "check": "tests",
            "method": "run",
            "status": "PASS",
            "evidence": ["executed"],
            "limitations": [],
            "execution": execution("python -m unittest legacy"),
        },
        "verification-review.json": {
            "schema_version": 2,
            "id": "V-REVIEW",
            "kind": "verification",
            "artifact_id": "A-1",
            "artifact_version": "1",
            "criterion_ids": ["AC-1"],
            "check": "review",
            "method": "inspect",
            "status": "PASS",
            "evidence": ["reviewed"],
            "limitations": [],
            "execution": execution("host-session: legacy review"),
        },
        "decision.json": {
            "schema_version": 2,
            "id": "D-1",
            "kind": "decision",
            "work_item_id": "WI-OLD",
            "artifact_versions": ["1"],
            "decision": "ACCEPT",
            "rationale": "verified",
            "evidence_refs": ["legacy free-text evidence"],
            "unresolved_disagreements": [],
            "approver": "controller",
            "criteria_evidence": {
                "AC-1": {
                    "verification_ids": ["V-1"],
                    "result": "PASS",
                },
            },
            "residual_risks": [],
            "review_independence": "independent",
        },
    }


def l3_records():
    records = stage2_records()
    records["work-item.json"].update({
        "risk_level": "high",
        "control_tier": "L3",
    })
    records["work-item.json"]["route_flags"]["irreversible"] = True
    records["decision.json"]["approver"] = "human-reviewer"
    artifact = records["artifact-2.json"]
    records["verification-challenger.json"] = {
        "schema_version": 3,
        "id": "V-CHALLENGE",
        "kind": "verification",
        "artifact_id": "A-1",
        "artifact_version": "2",
        "artifact_content_hash": artifact["content_hash"],
        "criterion_ids": ["AC-1"],
        "role": "challenger",
        "execution": execution("host-session: challenger"),
        "host_context": {
            "session_id": "challenger-session",
            "model": "challenger-model",
            "independence": "independent",
            "authentication": "unverified_host_attestation",
        },
        "check": "independent challenge",
        "method": "inspect boundary cases",
        "status": "PASS",
        "evidence": ["challenge completed"],
        "limitations": [],
    }
    records["decision.json"]["evidence_refs"] = [
        "V-1", "V-REVIEW", "V-CHALLENGE"]
    return rebind_record_hashes(records)


def l3_preapproval_records():
    records = l3_records()
    records.pop("decision.json")
    return records


def l3_with_approval(approval):
    records = l3_records()
    records["approval-test.json"] = approval
    records["decision.json"]["evidence_refs"].append(approval["id"])
    return rebind_record_hashes(records)


def legacy_v1_records():
    return {
        "work-item.json": {
            "schema_version": 1,
            "id": "WI-V1",
            "kind": "work_item",
            "goal": "migrate v1",
            "pack_id": "software-development",
            "constraints": [],
            "priority": "medium",
            "risk_level": "medium",
            "acceptance_criteria": ["works", "reviewed"],
            "open_questions": [],
        },
        "artifact.json": {
            "schema_version": 1,
            "id": "A-V1",
            "kind": "artifact",
            "artifact_type": "test",
            "version": "1",
            "content": "candidate",
            "source": "legacy-artifact",
            "work_item_id": "WI-V1",
        },
        "verification.json": {
            "schema_version": 1,
            "id": "V-1",
            "kind": "verification",
            "artifact_id": "A-V1",
            "artifact_version": "1",
            "check": "tests",
            "method": "run",
            "status": "PASS",
            "evidence": ["executed"],
            "execution": execution("python -m unittest legacy v1"),
        },
        "verification-review.json": {
            "schema_version": 1,
            "id": "V-REVIEW",
            "kind": "verification",
            "artifact_id": "A-V1",
            "artifact_version": "1",
            "check": "review",
            "method": "inspect",
            "status": "PASS",
            "evidence": ["reviewed"],
            "execution": execution("host-session: legacy v1 review"),
        },
        "decision.json": {
            "schema_version": 1,
            "id": "D-1",
            "kind": "decision",
            "work_item_id": "WI-V1",
            "artifact_versions": ["1"],
            "decision": "ACCEPT",
            "rationale": "verified",
            "evidence_refs": ["legacy evidence"],
            "unresolved_disagreements": [],
            "approver": "controller",
            "criteria_evidence": [
                {
                    "criterion": "works",
                    "verification_ids": ["V-1"],
                    "result": "PASS",
                },
                {
                    "criterion": "reviewed",
                    "verification_ids": ["V-1", "V-REVIEW"],
                    "result": "PASS",
                },
            ],
            "residual_risks": [],
            "review_independence": "independent",
        },
    }


def write_records(root, records):
    for path in root.rglob("*.json"):
        path.unlink()
    for record_name, value in records.items():
        path = root / record_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")


class CliTests(unittest.TestCase):
    def test_human_approval_runtime_unblocks_l3_accept(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            source_records = l3_preapproval_records()
            write_records(root, source_records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "Review complete; approve release.",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            approval = json.loads(p.stdout)
            self.assertEqual(approval["kind"], "approval")
            self.assertEqual(
                approval["artifact_content_hash"],
                source_records["artifact-2.json"]["content_hash"])
            records = l3_with_approval(approval)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_human_approval_requires_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            write_records(root, l3_preapproval_records())
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "Review complete.",
                "--confirm", "APPROVE A-1@1")
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertEqual(list(root.glob("approval-*.json")), [])

    def test_human_approval_requires_review_and_challenge_pass(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = l3_preapproval_records()
            records.pop("verification-review.json")
            records.pop("verification-challenger.json")
            write_records(root, records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "premature approval",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("reviewer, challenger", p.stderr)
            self.assertEqual(list(root.glob("approval-*.json")), [])

    def test_human_approval_rejects_ambiguous_lineage(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = l3_preapproval_records()
            records.pop("iterations/iteration-01.json")
            write_records(root, records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "ambiguous target",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("lineage", p.stderr)
            self.assertEqual(list(root.glob("approval-*.json")), [])

    def test_human_approval_requires_complete_criterion_coverage(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = l3_preapproval_records()
            records["work-item.json"]["acceptance_criteria"]["AC-2"] = (
                "second criterion")
            write_records(root, records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "coverage incomplete",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("coverage for AC-2", p.stderr)
            self.assertEqual(list(root.glob("approval-*.json")), [])

    def test_l3_review_provenance_requires_distinct_host_sessions(self):
        cases = [
            ("producer-context", lambda records: records[
                "artifact-2.json"].pop("producer_context"),
             "producer_context"),
            ("reviewer-context", lambda records: records[
                "verification-review.json"].pop("host_context"),
             "Reviewer host_context"),
            ("reviewer-producer-session", lambda records: records[
                "verification-review.json"]["host_context"].update(
                    session_id="producer-session"),
             "different host session"),
            ("reviewer-independence", lambda records: records[
                "verification-review.json"]["host_context"].update(
                    independence="non_independent"),
             "independent host attestation"),
            ("role-session-collision", lambda records: records[
                "verification-challenger.json"]["host_context"].update(
                    session_id="reviewer-session"),
             "distinct host sessions"),
        ]
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = l3_preapproval_records()
            write_records(root, records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "provenance baseline",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            records = l3_with_approval(json.loads(p.stdout))
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            for name, mutate, marker in cases:
                with self.subTest(name=name):
                    changed = json.loads(json.dumps(records))
                    mutate(changed)
                    rebind_record_hashes(changed)
                    write_records(root, changed)
                    p = run_cli("check-records", "--dir", root)
                    self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                    self.assertIn(marker, p.stderr)

    def test_l3_review_provenance_rejects_same_model_and_decoys(self):
        cases = [
            ("producer-model", lambda records: records[
                "verification-review.json"]["host_context"].update(
                    model="producer-model"),
             "different model"),
            ("role-model", lambda records: records[
                "verification-challenger.json"]["host_context"].update(
                    model="reviewer-model"),
             "distinct models"),
            ("unreferenced-decoy", lambda records: records.update({
                "verification-review-decoy.json": dict(
                    records["verification-review.json"],
                    id="V-REVIEW-DECOY",
                    host_context={
                        "session_id": "challenger-session",
                        "model": "challenger-model",
                        "independence": "independent",
                        "authentication": "unverified_host_attestation",
                    })
            }),
             "distinct host sessions"),
            ("closure-challenger", lambda records: records[
                "verification-challenger.json"].update(
                    closure_gate=True),
             "role"),
        ]
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = l3_preapproval_records()
            write_records(root, records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "provenance baseline",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            records = l3_with_approval(json.loads(p.stdout))
            write_records(root, records)
            for name, mutate, marker in cases:
                with self.subTest(name=name):
                    changed = json.loads(json.dumps(records))
                    mutate(changed)
                    rebind_record_hashes(changed)
                    write_records(root, changed)
                    p = run_cli("check-records", "--dir", root)
                    self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                    self.assertIn(marker, p.stderr)

    def test_human_approval_rejects_open_high_and_roleless_verifier(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = l3_preapproval_records()
            records["finding-open.json"] = {
                "schema_version": 3,
                "id": "F-OPEN",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "high",
                "target": "approval",
                "claim": "open blocker",
                "evidence": ["counterexample"],
                "impact": "cannot approve",
                "required_action": "repair first",
                "criterion_ids": ["AC-1"],
                "status": "open",
            }
            write_records(root, records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "must fail",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("open high/blocking", p.stderr)
            self.assertEqual(list(root.glob("approval-*.json")), [])

            records.pop("finding-open.json")
            records["verification.json"].pop("role")
            write_records(root, records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "must fail",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("Verifier coverage", p.stderr)
            self.assertEqual(list(root.glob("approval-*.json")), [])

    def test_human_approval_rejects_invalid_closed_finding_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = l3_preapproval_records()
            records["finding-invalid.json"] = {
                "schema_version": 3,
                "id": "F-INVALID",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "high",
                "target": "approval",
                "claim": "invalid regression",
                "evidence": ["counterexample"],
                "impact": "approval bypass",
                "required_action": "reject",
                "criterion_ids": ["AC-1"],
                "status": "resolved",
                "closure_gate": True,
                "prevention": {
                    "kind": "structure",
                    "action": "guard",
                    "evidence": ["test"],
                    "regression_verification_ids": ["V-MISSING"],
                },
            }
            write_records(root, records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "must fail",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("V-MISSING", p.stderr)
            self.assertEqual(list(root.glob("approval-*.json")), [])

    def test_approval_binds_the_reviewed_record_set(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = l3_preapproval_records()
            write_records(root, records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "reviewed set",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            approval = json.loads(p.stdout)
            self.assertIn("reviewed_set_digest", approval)
            records = l3_with_approval(approval)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

            records["verification.json"]["evidence"] = [
                "replaced after approval"
            ]
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("reviewed_set_digest", p.stderr)

    def test_challenger_finding_cannot_replace_pass(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = l3_preapproval_records()
            write_records(root, records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "approved",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            approval = json.loads(p.stdout)
            records = l3_with_approval(approval)
            records.pop("verification-challenger.json")
            records["decision.json"]["evidence_refs"].remove("V-CHALLENGE")
            records["finding-challenger.json"] = {
                "schema_version": 3,
                "id": "F-CHALLENGE",
                "kind": "finding",
                "source_role": "challenger",
                "severity": "low",
                "target": "challenge",
                "claim": "challenge is still open",
                "evidence": ["not closed"],
                "impact": "challenge is not complete",
                "required_action": "complete challenge",
                "criterion_ids": ["AC-1"],
                "status": "open",
            }
            records["decision.json"]["evidence_refs"].append("F-CHALLENGE")
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("PASS Challenger evidence", p.stderr)

    def test_migrate_records_dry_run_preserves_legacy_files(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            write_records(root, legacy_v2_records())
            before = {
                path.name: path.read_bytes()
                for path in root.glob("*.json")
            }
            p = run_cli(
                "migrate-records", "--dir", root,
                "--verification-role", "V-1=verifier",
                "--verification-role", "V-REVIEW=reviewer")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn('"mode": "dry-run"', p.stdout)
            after = {
                path.name: path.read_bytes()
                for path in root.glob("*.json")
            }
            self.assertEqual(before, after)

    def test_migrate_records_writes_valid_v3_and_backup(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            write_records(root, legacy_v2_records())
            p = run_cli(
                "migrate-records", "--dir", root, "--write",
                "--verification-role", "V-1=verifier",
                "--verification-role", "V-REVIEW=reviewer")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            output = json.loads(p.stdout)
            self.assertEqual(output["mode"], "write")
            self.assertEqual(output["changed"], 5)
            self.assertTrue(Path(output["backup"]).is_dir())
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            work_item = json.loads(
                (root / "work-item.json").read_text(encoding="utf-8"))
            self.assertEqual(work_item["control_tier"], "L2")
            self.assertEqual(
                json.loads((root / "verification-review.json").read_text(
                    encoding="utf-8"))["role"],
                "reviewer")
            decision = json.loads(
                (root / "decision.json").read_text(encoding="utf-8"))
            self.assertEqual(decision["cycle"], 1)
            self.assertTrue(decision["evidence_refs"])
            shutil.rmtree(output["backup"])

    def test_migrate_records_does_not_write_invalid_output(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = legacy_v2_records()
            records["artifact.json"].pop("work_item_id")
            write_records(root, records)
            before = {
                path.name: path.read_bytes()
                for path in root.glob("*.json")
            }
            before_backups = {
                path.name for path in root.parent.iterdir()
                if path.name.startswith(root.name + ".migration-backup-")
            }
            p = run_cli(
                "migrate-records", "--dir", root, "--write",
                "--verification-role", "V-1=verifier",
                "--verification-role", "V-REVIEW=reviewer")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("migration validation", p.stderr)
            after = {
                path.name: path.read_bytes()
                for path in root.glob("*.json")
            }
            self.assertEqual(before, after)
            after_backups = {
                path.name for path in root.parent.iterdir()
                if path.name.startswith(root.name + ".migration-backup-")
            }
            self.assertEqual(before_backups, after_backups)

    def test_migrate_records_converts_real_v1_shape(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            write_records(root, legacy_v1_records())
            p = run_cli(
                "migrate-records", "--dir", root, "--write",
                "--verification-role", "V-1=verifier",
                "--verification-role", "V-REVIEW=reviewer")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            output = json.loads(p.stdout)
            self.addCleanup(
                lambda: shutil.rmtree(
                    output["backup"], ignore_errors=True))
            work_item = json.loads(
                (root / "work-item.json").read_text(encoding="utf-8"))
            self.assertEqual(
                list(work_item["acceptance_criteria"]), ["AC-1", "AC-2"])
            decision = json.loads(
                (root / "decision.json").read_text(encoding="utf-8"))
            self.assertEqual(set(decision["criteria_evidence"]), {
                "AC-1", "AC-2"})
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_migrate_records_rolls_back_mid_commit_failure(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            write_records(root, legacy_v2_records())
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*.json")
            }
            original_replace = cli_module.os.replace
            calls = {"count": 0}

            def failing_replace(source, target):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise KeyboardInterrupt("injected commit failure")
                return original_replace(source, target)

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(
                    cli_module.os, "replace",
                    side_effect=failing_replace):
                with contextlib.redirect_stdout(stdout), \
                        contextlib.redirect_stderr(stderr):
                    code = cli_module.migrate_records(
                        root, True,
                        ["V-1=verifier", "V-REVIEW=reviewer"])
            self.assertEqual(code, 1)
            self.assertIn("migration commit failed", stderr.getvalue())
            after = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*.json")
            }
            self.assertEqual(before, after)

    def test_migrate_records_requires_explicit_unmapped_coverage(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = legacy_v1_records()
            records["verification-extra.json"] = {
                "schema_version": 1,
                "id": "V-EXTRA",
                "kind": "verification",
                "artifact_id": "A-V1",
                "artifact_version": "1",
                "check": "extra",
                "method": "run",
                "status": "PASS",
                "evidence": ["executed"],
                "execution": execution("python -m unittest extra"),
            }
            write_records(root, records)
            p = run_cli(
                "migrate-records", "--dir", root,
                "--verification-role", "V-1=verifier",
                "--verification-role", "V-REVIEW=reviewer",
                "--verification-role", "V-EXTRA=verifier")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("record-criteria", p.stderr)
            p = run_cli(
                "migrate-records", "--dir", root, "--write",
                "--verification-role", "V-1=verifier",
                "--verification-role", "V-REVIEW=reviewer",
                "--verification-role", "V-EXTRA=verifier",
                "--record-criteria", "V-EXTRA=AC-1")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            shutil.rmtree(json.loads(p.stdout)["backup"])

    def test_migrate_records_rejects_malformed_v1_evidence_ids(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = legacy_v1_records()
            records["decision.json"]["criteria_evidence"][0][
                "verification_ids"] = None
            write_records(root, records)
            p = run_cli(
                "migrate-records", "--dir", root,
                "--verification-role", "V-1=verifier",
                "--verification-role", "V-REVIEW=reviewer")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("verification_ids", p.stderr)
            self.assertNotIn("Traceback", p.stderr)

    def test_migrate_records_recovers_interrupted_journal(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            root = base / "records"
            root.mkdir()
            write_records(root, legacy_v2_records())
            backup = base / "records.migration-backup-test"
            stage = base / "records.migration-stage-test"
            shutil.copytree(root, backup)
            shutil.copytree(root, stage)
            journal = cli_module.migration_journal_path(root)
            journal.write_text(json.dumps({
                "schema_version": 1,
                "root": str(root.resolve()),
                "backup": str(backup.resolve()),
                "stage": str(stage.resolve()),
                "phase": "backed_up",
            }), encoding="utf-8")
            shutil.rmtree(root)
            stderr = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(stderr):
                code = cli_module.migrate_records(
                    root, False,
                    ["V-1=verifier", "V-REVIEW=reviewer"])
            self.assertEqual(code, 0, stderr.getvalue())
            self.assertTrue((root / "work-item.json").exists())
            self.assertFalse(stage.exists())
            self.assertFalse(journal.exists())

    def test_migrate_records_rejects_concurrent_writer(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            write_records(root, legacy_v2_records())
            fd, lock_path = cli_module.acquire_migration_lock(root)
            self.assertIsNotNone(fd)
            try:
                p = run_cli(
                    "migrate-records", "--dir", root,
                    "--verification-role", "V-1=verifier",
                    "--verification-role", "V-REVIEW=reviewer")
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("already active", p.stderr)
            finally:
                cli_module.release_migration_lock(fd, lock_path)
            self.assertTrue(lock_path.exists())
            fd, lock_path = cli_module.acquire_migration_lock(root)
            self.assertIsNotNone(fd)
            cli_module.release_migration_lock(fd, lock_path)

    def test_migration_journal_cannot_delete_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            root = base / "records"
            victim = base / "victim"
            root.mkdir()
            victim.mkdir()
            (victim / "keep.txt").write_text("keep", encoding="utf-8")
            journal = cli_module.migration_journal_path(root)
            journal.write_text(json.dumps({
                "schema_version": 1,
                "root": str(root.resolve()),
                "backup": str((base / "records.migration-backup-x").resolve()),
                "stage": str(victim.resolve()),
                "phase": "prepared",
            }), encoding="utf-8")
            recovered, error = cli_module.recover_migration_transaction(root)
            self.assertIsNone(recovered)
            self.assertIn("paths are invalid", error)
            self.assertTrue((victim / "keep.txt").exists())

    def test_migration_journal_non_string_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "records"
            root.mkdir()
            journal = cli_module.migration_journal_path(root)
            journal.write_text(json.dumps({
                "schema_version": 1,
                "root": str(root.resolve()),
                "backup": 1,
                "stage": [],
                "phase": "prepared",
            }), encoding="utf-8")
            recovered, error = cli_module.recover_migration_transaction(root)
            self.assertIsNone(recovered)
            self.assertIn("paths are invalid", error)

    def test_migrate_records_rejects_duplicate_mappings(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            write_records(root, legacy_v2_records())
            p = run_cli(
                "migrate-records", "--dir", root,
                "--verification-role", "V-1=verifier",
                "--verification-role", "V-1=reviewer")
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("duplicate --verification-role", p.stderr)
            p = run_cli(
                "migrate-records", "--dir", root,
                "--record-criteria", "V-1=AC-1",
                "--record-criteria", "V-1=AC-2")
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("duplicate --record-criteria", p.stderr)

    def test_runtime_checkpoint_resumes_from_canonical_records(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store"
            records_dir.mkdir()
            records = stage2_records()
            decision = records.pop("decision.json")
            write_records(records_dir, records)
            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", store)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            checkpoint = json.loads(p.stdout)
            self.assertEqual(checkpoint["state"], "DECIDE")

            records["decision.json"] = decision
            write_records(records_dir, records)
            p = run_cli(
                "runtime-resume", "--store", store,
                "--records", records_dir)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            resumed = json.loads(p.stdout)
            self.assertTrue(resumed["recovered"])
            self.assertEqual(resumed["checkpoint"]["state"], "ACCEPT")
            p = run_cli(
                "runtime-status", "--store", store,
                "--records", records_dir)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(json.loads(p.stdout)["state"], "ACCEPT")

    def test_runtime_skips_corrupt_checkpoint_and_rejects_embedded_store(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store"
            records_dir.mkdir()
            write_records(records_dir, stage2_records())
            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", store)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            checkpoints = store / "checkpoints"
            (checkpoints / "zzzz-corrupt.json").write_text(
                "{not-json", encoding="utf-8")
            p = run_cli(
                "runtime-resume", "--store", store,
                "--records", records_dir)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            resumed = json.loads(p.stdout)
            self.assertGreaterEqual(resumed["skipped_invalid"], 1)
            self.assertEqual(resumed["checkpoint"]["state"], "ACCEPT")

            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", records_dir / "runtime")
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("inside the records directory", p.stderr)

    def test_runtime_uses_lineage_and_failed_verification(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store"
            records_dir.mkdir()
            records = stage2_records()
            records["artifact-1.json"]["version"] = "9"
            records["artifact-2.json"]["version"] = "10"
            records["verification.json"]["artifact_version"] = "10"
            records["verification-review.json"]["artifact_version"] = "10"
            records["verification-repair-evidence.json"][
                "artifact_version"] = "9"
            records["decision-repair.json"]["artifact_versions"] = ["9"]
            records["decision.json"]["artifact_versions"] = ["10"]
            records["iterations/iteration-01.json"].update(
                input_versions=["9"], output_versions=["10"])
            rebind_record_hashes(records)
            write_records(records_dir, records)
            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", store)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            checkpoint = json.loads(p.stdout)
            self.assertEqual(checkpoint["artifact_versions"], ["9", "10"])
            self.assertEqual(checkpoint["state"], "ACCEPT")

            records["verification.json"]["status"] = "FAIL"
            records.pop("decision.json")
            write_records(records_dir, records)
            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", store)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(json.loads(p.stdout)["state"], "REPAIR")

    def test_runtime_requires_l3_challenge_and_approval(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store"
            records_dir.mkdir()
            records = l3_preapproval_records()
            records.pop("verification-challenger.json")
            write_records(records_dir, records)
            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", store)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(json.loads(p.stdout)["state"], "CHALLENGE")

            records = l3_preapproval_records()
            write_records(records_dir, records)
            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", store)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(json.loads(p.stdout)["state"], "RECONCILE")

    def test_runtime_requires_complete_criteria_and_lineage(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            records_dir.mkdir()
            records = stage2_records()
            records["work-item.json"]["acceptance_criteria"]["AC-2"] = (
                "second criterion")
            records.pop("decision.json")
            write_records(records_dir, records)
            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", base / "store")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(json.loads(p.stdout)["state"], "VERIFY")

            records.pop("iterations/iteration-01.json")
            write_records(records_dir, records)
            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", base / "store")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("lineage", p.stderr)

    def test_runtime_and_control_plane_reject_multiple_terminal_decisions(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store"
            records_dir.mkdir()
            records = stage2_records()
            for cycle, suffix in ((3, "A"), (4, "B")):
                records["decision-stop-{}.json".format(suffix.lower())] = {
                    "schema_version": 3,
                    "id": "D-STOP-" + suffix,
                    "kind": "decision",
                    "cycle": cycle,
                    "work_item_id": "WI-1",
                    "artifact_versions": ["2"],
                    "decision": "STOP",
                    "rationale": "duplicate terminal",
                    "evidence_refs": ["V-1"],
                    "unresolved_disagreements": [],
                    "approver": "controller",
                }
            rebind_record_hashes(records)
            write_records(records_dir, records)
            for args in (
                ("runtime-checkpoint", "--records", records_dir,
                 "--store", store),
                ("metrics", "--dir", records_dir),
                ("registry-update", "--store", store,
                 "--records", records_dir),
                ("improvements", "--dir", records_dir),
            ):
                p = run_cli(*args)
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertIn("terminal Decision", p.stderr)

    def test_runtime_and_control_plane_reject_invalid_closed_findings(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store"
            records_dir.mkdir()
            records = stage2_records()
            records["finding-invalid.json"] = {
                "schema_version": 3,
                "id": "F-INVALID",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "high",
                "target": "shared validation",
                "claim": "invalid closure",
                "evidence": ["counterexample"],
                "impact": "invalid records could persist",
                "required_action": "apply shared validation",
                "criterion_ids": ["AC-1"],
                "status": "resolved",
                "closure_gate": True,
                "prevention": {
                    "kind": "structure",
                    "action": "guard",
                    "evidence": ["test"],
                    "regression_verification_ids": ["V-MISSING"],
                },
            }
            rebind_record_hashes(records)
            write_records(records_dir, records)
            p = run_cli("check-records", "--dir", records_dir)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            for args in (
                ("runtime-checkpoint", "--records", records_dir,
                 "--store", store),
                ("metrics", "--dir", records_dir),
                ("registry-update", "--store", store,
                 "--records", records_dir),
                ("improvements", "--dir", records_dir),
            ):
                p = run_cli(*args)
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertIn("V-MISSING", p.stderr)

    def test_runtime_status_recovers_from_only_corrupt_checkpoints(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store" / "checkpoints"
            records_dir.mkdir()
            store.mkdir(parents=True)
            write_records(records_dir, stage2_records())
            (store / "only.json").write_text("{bad", encoding="utf-8")
            p = run_cli(
                "runtime-status", "--store", store.parent,
                "--records", records_dir)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            status = json.loads(p.stdout)
            self.assertEqual(status["state"], "ACCEPT")
            self.assertEqual(status["source"], "canonical_records_recovery")

    def test_runtime_rejects_tampered_semantics_and_embedded_resume_store(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store"
            records_dir.mkdir()
            write_records(records_dir, stage2_records())
            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", store)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            checkpoint_path = next((store / "checkpoints").glob("*.json"))
            checkpoint = json.loads(
                checkpoint_path.read_text(encoding="utf-8"))
            checkpoint["state"] = "STOP"
            checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
            p = run_cli(
                "runtime-status", "--store", store,
                "--records", records_dir)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            status = json.loads(p.stdout)
            self.assertEqual(status["state"], "ACCEPT")
            self.assertEqual(status["source"], "canonical_records_recovery")

            p = run_cli(
                "runtime-resume", "--store", records_dir / "runtime",
                "--records", records_dir)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("inside the records directory", p.stderr)

    def test_runtime_schema_errors_do_not_traceback(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            records_dir.mkdir()
            records = stage2_records()
            records["work-item.json"]["acceptance_criteria"] = None
            write_records(records_dir, records)
            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", base / "store")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("schema", p.stderr)
            self.assertNotIn("Traceback", p.stderr)

    def test_runtime_metrics_registry_reject_invalid_terminal_records(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store"
            records_dir.mkdir()
            write_records(records_dir, l3_preapproval_records())
            p = run_cli(
                "approve", "--records", records_dir,
                "--artifact", records_dir / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "approved",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            records = l3_with_approval(json.loads(p.stdout))
            records["decision.json"]["evidence_refs"] = ["V-1"]
            write_records(records_dir, records)
            p = run_cli("check-records", "--dir", records_dir)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            p = run_cli(
                "runtime-checkpoint", "--records", records_dir,
                "--store", store)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            p = run_cli("metrics", "--dir", records_dir)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            p = run_cli(
                "registry-update", "--store", store,
                "--records", records_dir)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)

    def test_metrics_and_improvement_candidates(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            records_dir.mkdir()
            records = stage2_records()
            records["finding-medium.json"] = {
                "schema_version": 3,
                "id": "F-MEDIUM",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "medium",
                "target": "latency",
                "claim": "latency is bounded but high",
                "evidence": ["observed 900 ms"],
                "impact": "slower than target",
                "required_action": "reduce latency",
                "criterion_ids": ["AC-1"],
                "status": "open",
            }
            records["verification-blocked.json"] = {
                "schema_version": 3,
                "id": "V-BLOCKED",
                "kind": "verification",
                "artifact_id": "A-1",
                "artifact_version": "2",
                "artifact_content_hash": records["artifact-2.json"][
                    "content_hash"],
                "criterion_ids": ["AC-1"],
                "role": "verifier",
                "check": "network check",
                "method": "run",
                "status": "BLOCKED",
                "evidence": ["network unavailable"],
                "limitations": ["network unavailable"],
            }
            records.pop("decision.json")
            write_records(records_dir, records)
            host_metrics = base / "host-metrics.json"
            host_metrics.write_text(json.dumps({
                "turns": 4,
                "tool_calls": 12,
                "total_tokens": 1400,
                "cost_usd": 0.25,
            }), encoding="utf-8")
            output = base / "metrics.json"
            p = run_cli(
                "metrics", "--dir", records_dir,
                "--host-metrics", host_metrics, "--output", output)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            metrics = json.loads(p.stdout)
            self.assertEqual(metrics["record_count"], 10)
            self.assertEqual(metrics["artifact_versions"], ["1", "2"])
            self.assertEqual(metrics["verification_statuses"]["BLOCKED"], 1)
            self.assertEqual(metrics["host_metrics"]["total_tokens"], 1400)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["state"],
                "VERIFY")

            p = run_cli("improvements", "--dir", records_dir)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            candidates = json.loads(p.stdout)["candidates"]
            categories = {item["category"] for item in candidates}
            self.assertIn("resolve_medium_finding", categories)
            self.assertIn("stabilize_check", categories)

    def test_version_registry_deduplicates_runs(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store"
            records_dir.mkdir()
            write_records(records_dir, stage2_records())
            p = run_cli(
                "registry-update", "--store", store,
                "--records", records_dir, "--label", "local")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            first = json.loads(p.stdout)
            p = run_cli(
                "registry-update", "--store", store,
                "--records", records_dir, "--label", "local")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(json.loads(p.stdout), first)
            p = run_cli("registry-list", "--store", store)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            registry = json.loads(p.stdout)
            self.assertEqual(len(registry["runs"]), 1)
            self.assertEqual(
                registry["runs"][0]["artifact_versions"], ["1", "2"])
            self.assertEqual(registry["runs"][0]["state"], "ACCEPT")
            self.assertEqual(
                len(list((store / "registry" / "runs").glob("*.json"))), 1)

    def test_registry_rejects_same_digest_provenance_conflict(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store"
            records_dir.mkdir()
            write_records(records_dir, stage2_records())
            p = run_cli(
                "registry-update", "--store", store,
                "--records", records_dir, "--label", "local",
                "--commit", "abc123")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            original = json.loads(p.stdout)
            entry_path = next((store / "registry" / "runs").glob("*.json"))
            p = run_cli(
                "registry-update", "--store", store,
                "--records", records_dir, "--label", "remote",
                "--commit", "abc123")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("provenance conflict", p.stderr)
            self.assertEqual(
                json.loads(entry_path.read_text(encoding="utf-8")),
                original)
            p = run_cli("registry-list", "--store", store)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(json.loads(p.stdout)["runs"], [original])

    def test_registry_same_digest_concurrent_conflict_keeps_one_provenance(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            store = base / "store"
            records_dir.mkdir()
            write_records(records_dir, stage2_records())
            processes = [
                subprocess.Popen([
                    sys.executable, str(CLI), "registry-update",
                    "--store", str(store), "--records", str(records_dir),
                    "--label", label,
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for label in ("A", "B")
            ]
            outputs = [process.communicate(timeout=30) for process in processes]
            for process, (stdout, stderr) in zip(processes, outputs):
                self.assertNotIn("Traceback", stderr)
            self.assertEqual(
                sorted(process.returncode for process in processes), [0, 1])
            p = run_cli("registry-list", "--store", store)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            runs = json.loads(p.stdout)["runs"]
            self.assertEqual(len(runs), 1)
            self.assertIn(runs[0]["label"], {"A", "B"})

    def test_registry_list_rejects_malformed_legacy_entries(self):
        with tempfile.TemporaryDirectory() as t:
            store = Path(t)
            (store / "registry.json").write_text(
                json.dumps({"runs": [None]}), encoding="utf-8")
            p = run_cli("registry-list", "--store", store)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("legacy registry run must be an object", p.stderr)
            self.assertNotIn("Traceback", p.stderr)

    def test_metrics_reject_cross_work_approval_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            records_dir = base / "records"
            records_dir.mkdir()
            records = stage2_records()
            records["approval-other.json"] = {
                "schema_version": 3,
                "id": "AP-OTHER",
                "kind": "approval",
                "work_item_id": "WI-OTHER",
                "artifact_id": "A-1",
                "artifact_version": "2",
                "artifact_content_hash": records["artifact-2.json"][
                    "content_hash"],
                "reviewed_set_digest": records["decision.json"][
                    "reviewed_set_digest"],
                "approver": "human",
                "statement": "other run",
                "approved_at": "2026-11-15T09:00:00+08:00",
                "confirmation": "APPROVE A-1@2",
                "authentication": "unverified_host_attestation",
            }
            write_records(records_dir, records)
            p = run_cli("metrics", "--dir", records_dir)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("Approval work_item_id", p.stderr)

            records.pop("approval-other.json")
            write_records(records_dir, records)
            host = base / "host.json"
            host.write_text('{"turns": NaN}', encoding="utf-8")
            p = run_cli(
                "metrics", "--dir", records_dir,
                "--host-metrics", host)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("non-negative number", p.stderr)

            p = run_cli(
                "metrics", "--dir", records_dir,
                "--output", records_dir / "metrics.json")
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("inside the records directory", p.stderr)
            p = run_cli(
                "improvements", "--dir", records_dir,
                "--output", records_dir / "improvements.json")
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("inside the records directory", p.stderr)
            p = run_cli("check-records", "--dir", records_dir)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_registry_concurrent_updates_preserve_both_runs(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            store = base / "store"
            record_dirs = []
            for suffix in ("A", "B"):
                records_dir = base / ("records-" + suffix)
                records_dir.mkdir()
                records = stage2_records()
                work_item_id = "WI-" + suffix
                records["work-item.json"]["id"] = work_item_id
                for record in records.values():
                    if record.get("work_item_id") == "WI-1":
                        record["work_item_id"] = work_item_id
                rebind_record_hashes(records)
                write_records(records_dir, records)
                record_dirs.append(records_dir)
            processes = [
                subprocess.Popen([
                    sys.executable, str(CLI), "registry-update",
                    "--store", str(store), "--records", str(records_dir),
                    "--label", records_dir.name,
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for records_dir in record_dirs
            ]
            outputs = [process.communicate(timeout=30) for process in processes]
            for process, (stdout, stderr) in zip(processes, outputs):
                self.assertEqual(process.returncode, 0, stdout + stderr)
            p = run_cli("registry-list", "--store", store)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(len(json.loads(p.stdout)["runs"]), 2)

    def test_legacy_migration_manifest_metadata_is_enforced(self):
        records = [
            {"id": "V-1", "kind": "verification"},
            {"id": "V-2", "kind": "verification", "role": "reviewer"},
            {"id": "A-1", "kind": "artifact"},
        ]
        migration = {
            "work_item_id": "WI-LEGACY",
            "from_schema_version": 2,
            "to_schema_version": 3,
            "record_count": 3,
            "records_sha256": cli_module.records_sha256(records),
            "pre_migration_snapshot_retained": False,
            "role_fields_present_before_rewrite": {
                "V-2": "reviewer"
            },
            "roleless_verification_ids": ["V-1"],
            "disclosure": "available state frozen",
        }
        manifest = {
            "schema_version": 1,
            "digest_algorithm": (
                "SHA-256 over sorted compact JSON records joined by LF"),
            "migrations": [migration],
        }
        original = cli_module.MIGRATION_MANIFEST
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "v2-to-v3.json"
            cli_module.MIGRATION_MANIFEST = path
            try:
                path.write_text(json.dumps(manifest), encoding="utf-8")
                self.assertEqual(
                    ({"V-1"}, None),
                    cli_module.legacy_roleless_ids(records, "WI-LEGACY"))

                invalid = dict(manifest, migrations=[
                    dict(migration, record_count=0)
                ])
                path.write_text(json.dumps(invalid), encoding="utf-8")
                self.assertIn(
                    "record_count",
                    cli_module.legacy_roleless_ids(
                        records, "WI-LEGACY")[1])

                invalid = dict(manifest, migrations=[
                    dict(migration, from_schema_version=999)
                ])
                path.write_text(json.dumps(invalid), encoding="utf-8")
                self.assertIn(
                    "2 to 3",
                    cli_module.legacy_roleless_ids(
                        records, "WI-LEGACY")[1])

                invalid = dict(manifest, migrations=[
                    dict(migration, role_fields_present_before_rewrite={})
                ])
                path.write_text(json.dumps(invalid), encoding="utf-8")
                self.assertIn(
                    "role disclosure",
                    cli_module.legacy_roleless_ids(
                        records, "WI-LEGACY")[1])

                invalid = dict(manifest, migrations=[
                    dict(migration, roleless_verification_ids=[])
                ])
                path.write_text(json.dumps(invalid), encoding="utf-8")
                self.assertIn(
                    "roleless IDs",
                    cli_module.legacy_roleless_ids(
                        records, "WI-LEGACY")[1])

                invalid = dict(manifest, schema_version=True)
                path.write_text(json.dumps(invalid), encoding="utf-8")
                self.assertIn(
                    "schema_version",
                    cli_module.legacy_roleless_ids(
                        records, "WI-LEGACY")[1])

                invalid = dict(manifest, migrations=[
                    dict(migration, record_count=3.0)
                ])
                path.write_text(json.dumps(invalid), encoding="utf-8")
                self.assertIn(
                    "record_count",
                    cli_module.legacy_roleless_ids(
                        records, "WI-LEGACY")[1])

                invalid = dict(manifest, migrations=[
                    dict(migration, from_schema_version=2.0)
                ])
                path.write_text(json.dumps(invalid), encoding="utf-8")
                self.assertIn(
                    "2 to 3",
                    cli_module.legacy_roleless_ids(
                        records, "WI-LEGACY")[1])

                invalid = dict(manifest, migrations=[migration, migration])
                path.write_text(json.dumps(invalid), encoding="utf-8")
                self.assertIn(
                    "duplicate",
                    cli_module.legacy_roleless_ids(
                        records, "WI-LEGACY")[1])
            finally:
                cli_module.MIGRATION_MANIFEST = original

    def test_doctor(self):
        p = run_cli("doctor", "--root", CLI.parents[1])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Python:", p.stdout)
        self.assertIn("core/protocol.md: present", p.stdout)
        self.assertIn("roles/challenger.md: present", p.stdout)
        self.assertIn("packs/architecture-design/pack.md: present", p.stdout)
        self.assertIn("loop_engineering/cli.py: present", p.stdout)

    def test_artifact_schemas_are_valid_json(self):
        schema_root = CLI.parents[1] / "core" / "artifact-schema"
        expected = {
            "work-item.schema.json",
            "artifact.schema.json",
            "finding.schema.json",
            "verification.schema.json",
            "decision.schema.json",
            "iteration.schema.json",
            "approval.schema.json",
        }
        self.assertEqual({p.name for p in schema_root.glob("*.schema.json")}, expected)
        for path in schema_root.glob("*.schema.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(data["type"], "object")
            self.assertEqual(data["properties"]["schema_version"]["const"], 3)

    def test_artifact_schema_requires_versioned_file_list(self):
        path = CLI.parents[1] / "core" / "artifact-schema" / "artifact.schema.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("files", data["required"])
        files = data["properties"]["files"]
        self.assertEqual(files["type"], "array")
        self.assertTrue(files["uniqueItems"])
        self.assertEqual(files["items"]["pattern"], "\\S")
        self.assertEqual(
            data["properties"]["id"]["pattern"],
            "^[A-Za-z][A-Za-z0-9._-]*$")
        self.assertEqual(
            data["properties"]["work_item_id"]["pattern"],
            "^[A-Za-z][A-Za-z0-9._-]*$")
        for field in ("artifact_type", "version", "content", "source"):
            self.assertEqual(data["properties"][field]["pattern"], "\\S")
        self.assertIn("content_hash", data["required"])
        self.assertEqual(
            data["properties"]["content_hash"]["pattern"],
            "^[0-9a-f]{64}$")

    def test_check_records_rejects_stale_artifact_hashes(self):
        cases = [
            ("artifact", "artifact-2.json",
             lambda value: value.update(content="replaced"),
             "content_hash"),
            ("verification", "verification.json",
             lambda value: value.update(artifact_content_hash="0" * 64),
             "artifact content hash"),
            ("decision", "decision.json",
             lambda value: value["artifact_hashes"].update({"2": "0" * 64}),
             "artifact hash"),
            ("missing-decision-hash", "decision.json",
             lambda value: value["artifact_hashes"].pop("2"),
             "artifact_hashes"),
        ]
        for name, filename, mutate, marker in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as t:
                root = Path(t)
                records = stage2_records()
                mutate(records[filename])
                write_records(root, records)
                p = run_cli("check-records", "--dir", root)
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertIn(marker, p.stderr)

    def test_final_verification_requires_executed_command_metadata(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = stage2_records()
            records["verification.json"].pop("execution")
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("execution", p.stderr)

            records = l3_preapproval_records()
            records["verification-review.json"].pop("execution")
            write_records(root, records)
            p = run_cli(
                "approve", "--records", root,
                "--artifact", root / "artifact-2.json",
                "--approver", "human-reviewer",
                "--statement", "missing execution",
                "--confirm", "APPROVE A-1@2")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("execution", p.stderr)
            self.assertEqual(list(root.glob("approval-*.json")), [])

    def test_pre_closure_check_bootstraps_record_closure_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = stage2_records()
            records["finding-closure.json"] = {
                "schema_version": 3,
                "id": "F-CLOSURE",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "high",
                "target": "records",
                "claim": "records need closure",
                "evidence": ["not yet closed"],
                "impact": "audit gap",
                "required_action": "run record closure",
                "criterion_ids": ["AC-1"],
                "status": "resolved",
                "closure_gate": True,
                "prevention": {
                    "kind": "structure",
                    "action": "run closure gate",
                    "evidence": ["test"],
                    "regression_verification_ids": ["V-CLOSURE"],
                },
            }
            records["verification-closure.json"] = {
                "schema_version": 3,
                "id": "V-CLOSURE",
                "kind": "verification",
                "artifact_id": "A-1",
                "artifact_version": "2",
                "artifact_content_hash": "",
                "closure_gate": True,
                "finding_id": "F-CLOSURE",
                "criterion_ids": ["AC-1"],
                "role": "verifier",
                "check": "record closure",
                "method": "check-records --pre-closure",
                "status": "NOT_RUN",
                "evidence": ["bootstrap phase"],
                "limitations": [],
                "execution": execution("check-records --pre-closure"),
            }
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli(
                "check-records", "--dir", root, "--pre-closure")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("not PASS", p.stderr)

            records["verification-closure.json"]["status"] = "PASS"
            records["verification-closure.json"]["evidence"] = [
                "closure check executed"
            ]
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli(
                "check-finding", "--input", root / "finding-closure.json",
                "--work-item", root / "work-item.json",
                "--artifact", root / "artifact-2.json",
                "--verifications-dir", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            records["verification-closure.json"]["status"] = "NOT_RUN"
            records["verification-closure.json"]["evidence"] = [
                "bootstrap phase"
            ]
            rebind_record_hashes(records)
            write_records(root, records)

            records["decision.json"]["criteria_evidence"]["AC-1"][
                "verification_ids"] = ["V-CLOSURE"]
            write_records(root, records)
            p = run_cli(
                "check-records", "--dir", root, "--pre-closure")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("Verifier Verification role", p.stderr)

    def test_check_records_verifies_working_tree_source_files(self):
        if shutil.which("git") is None:
            self.skipTest("git is unavailable")
        with tempfile.TemporaryDirectory() as t:
            repo = Path(t) / "repo"
            records_dir = Path(t) / "records"
            repo.mkdir()
            records_dir.mkdir()
            source = repo / "source.txt"
            source.write_text("reviewed content\n", encoding="utf-8")
            for argv in (
                ("git", "init"),
                ("git", "config", "user.name", "test"),
                ("git", "config", "user.email", "test@example.com"),
                ("git", "add", "source.txt"),
                ("git", "commit", "-m", "source"),
            ):
                p = subprocess.run(
                    argv, cwd=repo, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            source_hash = hashlib.sha256(subprocess.check_output(
                ["git", "show", "{}:source.txt".format(revision)],
                cwd=repo)).hexdigest()
            records = stage2_records()
            for name, record in records.items():
                if record.get("kind") == "artifact":
                    record.update({
                        "artifact_type": "working_tree_change",
                        "files": ["source.txt"],
                        "source_revision": revision,
                        "file_hashes": {"source.txt": source_hash},
                    })
            rebind_record_hashes(records)
            write_records(records_dir, records)
            p = run_cli(
                "check-records", "--dir", records_dir, "--repo", repo)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

            source.write_text("UNREVIEWED replacement\n", encoding="utf-8")
            p = run_cli(
                "check-records", "--dir", records_dir, "--repo", repo)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("working tree", p.stderr)
            source.write_text("reviewed content\n", encoding="utf-8")

            for name, record in records.items():
                if record.get("kind") == "artifact":
                    record["file_hashes"]["source.txt"] = "0" * 64
            rebind_record_hashes(records)
            write_records(records_dir, records)
            p = run_cli(
                "check-records", "--dir", records_dir, "--repo", repo)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("source file hash", p.stderr)

    def test_migration_binds_artifact_hashes(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            write_records(root, legacy_v2_records())
            p = run_cli(
                "migrate-records", "--dir", root, "--write",
                "--verification-role", "V-1=verifier",
                "--verification-role", "V-REVIEW=reviewer")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            artifact = json.loads(
                (root / "artifact.json").read_text(encoding="utf-8"))
            verification = json.loads(
                (root / "verification.json").read_text(encoding="utf-8"))
            decision = json.loads(
                (root / "decision.json").read_text(encoding="utf-8"))
            self.assertEqual(
                artifact["content_hash"],
                bind_artifact(artifact)["content_hash"])
            self.assertEqual(
                verification["artifact_content_hash"],
                artifact["content_hash"])
            self.assertEqual(
                decision["artifact_hashes"],
                {"1": artifact["content_hash"]})

    def test_migration_upgrades_legacy_v3_identity_fields(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = stage2_records()
            for record in records.values():
                if record.get("kind") == "artifact":
                    record.pop("content_hash")
                    record.pop("producer_context", None)
                elif record.get("kind") == "verification":
                    record.pop("artifact_content_hash")
                    record.pop("role")
                    record.pop("execution", None)
                elif record.get("kind") == "decision":
                    record.pop("artifact_hashes")
            write_records(root, records)
            p = run_cli(
                "migrate-records", "--dir", root, "--write",
                "--verification-role", "V-1=verifier",
                "--verification-role", "V-REVIEW=reviewer",
                "--verification-role", "V-REPAIR-EVIDENCE=verifier")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("--execution-evidence", p.stderr)
            self.assertNotIn(
                "content_hash",
                (root / "artifact-1.json").read_text(encoding="utf-8"))

            evidence = root.parent / "execution-evidence.json"
            evidence.write_text(json.dumps({
                "V-1": execution("python -m unittest v3"),
                "V-REVIEW": execution("host-session: v3 review"),
                "V-REPAIR-EVIDENCE": execution("python -m unittest v3 repair"),
            }), encoding="utf-8")
            p = run_cli(
                "migrate-records", "--dir", root, "--write",
                "--verification-role", "V-1=verifier",
                "--verification-role", "V-REVIEW=reviewer",
                "--verification-role", "V-REPAIR-EVIDENCE=verifier",
                "--execution-evidence", evidence)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            for path in root.glob("artifact-*.json"):
                artifact = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    artifact["content_hash"],
                    bind_artifact(artifact)["content_hash"])
            for path in root.glob("verification*.json"):
                verification = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("artifact_content_hash", verification)
                self.assertIn("role", verification)
                self.assertIn("execution", verification)
            for path in root.glob("decision*.json"):
                decision = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("artifact_hashes", decision)

    def test_record_id_and_text_schemas_reject_blank(self):
        root = CLI.parents[1] / "core" / "artifact-schema"
        checks = [
            ("work-item.schema.json", "id",
             "^[A-Za-z][A-Za-z0-9._-]*$"),
            ("verification.schema.json", "id",
             "^[A-Za-z][A-Za-z0-9._-]*$"),
            ("iteration.schema.json", "id",
             "^[A-Za-z][A-Za-z0-9._-]*$"),
            ("iteration.schema.json", "work_item_id",
             "^[A-Za-z][A-Za-z0-9._-]*$"),
        ]
        for name, field, pattern in checks:
            data = json.loads((root / name).read_text(encoding="utf-8"))
            self.assertEqual(data["properties"][field]["pattern"], pattern)

    def test_decision_schema_encodes_gate_contract(self):
        path = CLI.parents[1] / "core" / "artifact-schema" / "decision.schema.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["properties"]["evidence_refs"]["minItems"], 1)
        self.assertIn("next_state", data["properties"])
        self.assertIn("repair_kind", data["properties"])
        conditions = data["allOf"]
        accept_rule = next(x for x in conditions
                           if x["if"]["properties"]["decision"]["const"] == "ACCEPT")
        repair_rule = next(x for x in conditions
                           if x["if"]["properties"]["decision"]["const"] == "REPAIR")
        self.assertIn("criteria_evidence", accept_rule["then"]["required"])
        criteria_evidence = data["properties"]["criteria_evidence"]
        self.assertEqual(criteria_evidence["type"], "object")
        self.assertEqual(criteria_evidence["minProperties"], 1)
        self.assertIn("pattern", criteria_evidence["propertyNames"])
        self.assertIn("residual_risks", accept_rule["then"]["required"])
        self.assertIn("review_independence", accept_rule["then"]["required"])
        self.assertIn("next_state", repair_rule["then"]["required"])
        self.assertIn("repair_kind", repair_rule["then"]["required"])
        criteria = criteria_evidence["additionalProperties"]
        self.assertEqual(criteria["required"], ["verification_ids", "result"])
        self.assertNotIn("criterion_id", criteria["properties"])
        self.assertEqual(criteria["properties"]["result"]["const"], "PASS")
        self.assertEqual(
            criteria["properties"]["verification_ids"]["items"]["pattern"],
            "^[A-Za-z][A-Za-z0-9._-]*$")
        self.assertEqual(data["properties"]["rationale"]["pattern"], "\\S")
        self.assertEqual(
            data["properties"]["evidence_refs"]["items"]["pattern"],
            "^[A-Za-z][A-Za-z0-9._-]*$")
        self.assertIn("evidence_notes", data["properties"])
        self.assertEqual(accept_rule["then"]["properties"]["unresolved_disagreements"]["maxItems"], 0)

    def test_high_findings_cannot_be_accepted_risk(self):
        path = CLI.parents[1] / "core" / "artifact-schema" / "finding.schema.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        rule = data["allOf"][0]
        self.assertIn("high", rule["if"]["properties"]["severity"]["enum"])
        self.assertNotIn("accepted_risk", rule["then"]["properties"]["status"]["enum"])
        prevention_rule = next(
            item for item in data["allOf"]
            if "prevention" in item.get("then", {}).get("required", []))
        self.assertEqual(
            prevention_rule["if"]["properties"]["status"]["enum"],
            ["resolved", "not_reproducible"])
        prevention = data["properties"]["prevention"]
        self.assertEqual(
            prevention["required"],
            ["kind", "action", "evidence", "regression_verification_ids"])
        self.assertEqual(
            prevention["properties"]["kind"]["enum"],
            ["structure", "automatic_check", "skill_rule", "human_review"])
        self.assertIn("regression_verification_ids",
                      prevention["properties"])
        self.assertIn("criterion_ids", data["required"])
        self.assertEqual(
            data["properties"]["criterion_ids"]["items"]["pattern"],
            "^[A-Za-z][A-Za-z0-9._-]*$")
        self.assertEqual(
            prevention["properties"]["action"]["pattern"], "\\S")
        self.assertEqual(
            prevention["properties"]["evidence"]["items"]["pattern"], "\\S")
        self.assertEqual(
            prevention["properties"]["regression_verification_ids"]["items"]["pattern"],
            "^[A-Za-z][A-Za-z0-9._-]*$")
        self.assertEqual(
            prevention["properties"]["fallback_reason"]["pattern"], "\\S")
        self.assertEqual(
            data["properties"]["recurrence_of"]["pattern"],
            "^[A-Za-z][A-Za-z0-9._-]*$")
        self.assertEqual(
            data["properties"]["id"]["pattern"],
            "^[A-Za-z][A-Za-z0-9._-]*$")
        fallback_rule = next(
            item for item in prevention["allOf"]
            if "fallback_reason" in item["then"]["required"])
        self.assertEqual(
            fallback_rule["if"]["properties"]["kind"]["enum"],
            ["automatic_check", "skill_rule", "human_review"])
        recurrence_rule = next(
            item for item in data["allOf"]
            if "recurrence_of" in item["if"].get("required", []))
        self.assertIn("prevention", recurrence_rule["then"]["required"])
        self.assertNotIn("status", recurrence_rule["if"]["required"])
        self.assertIn("recurrence_of", data["properties"])

    def test_verification_schema_links_artifact_version(self):
        path = CLI.parents[1] / "core" / "artifact-schema" / "verification.schema.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("artifact_id", data["required"])
        self.assertIn("artifact_version", data["required"])
        self.assertIn("criterion_ids", data["required"])
        self.assertIn("limitations", data["required"])
        self.assertIn("finding_id", data["properties"])
        self.assertEqual(
            data["properties"]["finding_id"]["pattern"],
            "^[A-Za-z][A-Za-z0-9._-]*$")
        limitations = data["properties"]["limitations"]
        self.assertEqual(limitations["type"], "array")
        self.assertEqual(limitations["items"]["type"], "string")
        self.assertEqual(limitations["items"]["pattern"], "\\S")
        self.assertEqual(data["properties"]["check"]["pattern"], "\\S")
        self.assertEqual(data["properties"]["method"]["pattern"], "\\S")
        self.assertEqual(data["properties"]["evidence"]["items"]["pattern"], "\\S")
        criteria = data["properties"]["criterion_ids"]
        self.assertEqual(criteria["minItems"], 1)
        self.assertTrue(criteria["uniqueItems"])

    def test_work_item_acceptance_criteria_have_stable_ids(self):
        root = CLI.parents[1]
        path = root / "core" / "artifact-schema" / "work-item.schema.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        criteria = data["properties"]["acceptance_criteria"]
        self.assertEqual(criteria["type"], "object")
        self.assertEqual(criteria["minProperties"], 1)
        self.assertIn("pattern", criteria["propertyNames"])
        self.assertEqual(criteria["additionalProperties"]["type"], "string")
        self.assertIn("max_repair_iterations", data["required"])
        self.assertEqual(
            data["properties"]["max_repair_iterations"]["type"], "integer")
        self.assertEqual(
            data["properties"]["max_repair_iterations"]["minimum"], 0)
        self.assertEqual(criteria["additionalProperties"]["pattern"], "\\S")

        schema_readme = (root / "core" / "artifact-schema" / "README.md").read_text(
            encoding="utf-8")
        self.assertIn("# Artifact Schema v3", schema_readme)
        self.assertIn("criterion_id", schema_readme)
        self.assertIn("This is a breaking schema upgrade", schema_readme)

        role_docs = [
            root / ".codex" / "agents" / "verifier.toml",
            root / ".codex" / "agents" / "arbiter.toml",
            root / ".claude" / "agents" / "verifier.md",
            root / ".claude" / "agents" / "arbiter.md",
        ]
        for path in role_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("criterion_ids", text)

    def test_decision_docs_limit_pass_mapping_to_accept(self):
        root = CLI.parents[1]
        skills = [root / ".agents" / "skills" / "loop-engineering" / "SKILL.md",
                  root / ".claude" / "skills" / "loop-engineering" / "SKILL.md"]
        for path in skills:
            text = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn("For `ACCEPT`, include each `criterion_id` mapped to "
                          "passing `verification_ids`", text)

    def test_full_mode_persists_only_on_explicit_request(self):
        root = CLI.parents[1]
        workflow = (root / "workflows" / "iterative-delivery" / "workflow.md").read_text(
            encoding="utf-8")
        normalized = " ".join(workflow.split())
        self.assertIn("Keep canonical role records in-session unless the project "
                      "explicitly requests persistence", normalized)
        self.assertIn("Do not create a Work Item or Artifact record", normalized)
        self.assertIn("run every check required by the selected pack", normalized)
        self.assertIn("A persistence request does not override compact",
                      normalized)

        skills = [root / ".agents" / "skills" / "loop-engineering" / "SKILL.md",
                  root / ".claude" / "skills" / "loop-engineering" / "SKILL.md"]
        for path in skills:
            text = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn("Keep canonical role records in-session unless the "
                          "project explicitly requests persistence", text)
        for path in (root / "AGENTS.md", root / "CLAUDE.md"):
            text = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn("A persistence request does not override compact",
                          text)
        self.assertIn(
            "verify --root . --report-dir",
            (root / "README.md").read_text(encoding="utf-8"))
        installed_docs = skills + [
            root / "adapters" / "codex" / "README.md",
            root / "adapters" / "claude-code" / "README.md",
        ]
        for path in installed_docs:
            text = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn(
                "python <installed-skill-root>/loop_engineering/cli.py "
                "doctor --mode installed", text)

    def test_check_finding_enforces_prevention_gate(self):
        base = {
            "schema_version": 3,
            "id": "F-1",
            "kind": "finding",
            "source_role": "reviewer",
            "severity": "high",
            "target": "gate",
            "claim": "unsafe",
            "evidence": ["counterexample"],
            "impact": "delivery can pass incorrectly",
            "required_action": "add guard",
            "criterion_ids": ["AC-1"],
            "status": "resolved"
        }
        cases = [
            (base, 1, "prevention"),
            (dict(base, status="not_reproducible"), 1, "prevention"),
            (dict(base, status="open"), 0, "PASS"),
            (dict(base, id="", prevention={
                "kind": "automatic_check",
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1"]
            }), 1, "id"),
            (dict(base, id="F-1\n[PASS] forged", prevention={
                "kind": "structure",
                "action": "remove invalid state",
                "evidence": ["schema"],
                "regression_verification_ids": ["V-1"]
            }), 1, "stable ID"),
            (dict(base, target="   ", prevention={
                "kind": "structure",
                "action": "remove invalid state",
                "evidence": ["schema"],
                "regression_verification_ids": ["V-1"]
            }), 1, "target"),
            (dict(base, source_role="attacker", prevention={
                "kind": "automatic_check",
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1"]
            }), 1, "source_role"),
            (dict(base, source_role=[], prevention={
                "kind": "automatic_check",
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1"]
            }), 1, "source_role"),
            (dict(base, severity={}, prevention={
                "kind": "automatic_check",
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1"]
            }), 1, "severity"),
            (dict(base, status=[], prevention={
                "kind": "automatic_check",
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1"]
            }), 1, "status"),
            (dict(base, prevention={
                "kind": [],
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1"]
            }), 1, "prevention kind"),
            (dict(base, prevention={
                "kind": "structure",
                "action": "remove invalid state",
                "evidence": ["schema"],
                "regression_verification_ids": [{}]
            }), 1, "stable ID"),
            (dict(base, evidence=[], prevention={
                "kind": "automatic_check",
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1"]
            }), 1, "evidence"),
            (dict(base, prevention={
                "kind": "structure",
                "action": "remove invalid state",
                "evidence": ["schema"]
            }), 1, "regression_verification_ids"),
            (dict(base, recurrence_of="F-0", severity="medium"), 1,
             "prevention"),
            (dict(base, recurrence_of="F-0", severity="medium", status="open"),
             1, "prevention"),
            (dict(base, recurrence_of="F-1", prevention={
                "kind": "structure",
                "action": "remove invalid state",
                "evidence": ["schema"],
                "regression_verification_ids": ["V-1"]
            }), 1, "self-referential"),
            (dict(base, recurrence_of=None, prevention={
                "kind": "automatic_check",
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1"]
            }), 1, "recurrence_of"),
            (dict(base, prevention={
                "kind": "human_review",
                "action": "inspect manually",
                "evidence": ["review"],
                "regression_verification_ids": ["V-1", "V-1"]
            }), 1, "must be unique"),
            (dict(base, prevention={
                "kind": "human_review",
                "action": "   ",
                "evidence": ["review"],
                "regression_verification_ids": ["V-1"],
                "fallback_reason": "semantic gap"
            }), 1, "action"),
            (dict(base, prevention={
                "kind": "human_review",
                "action": "inspect manually",
                "evidence": ["   "],
                "regression_verification_ids": ["V-1"],
                "fallback_reason": "semantic gap"
            }), 1, "evidence"),
            (dict(base, prevention={
                "kind": "human_review",
                "action": "inspect manually",
                "evidence": ["review"],
                "regression_verification_ids": ["V-1"],
                "fallback_reason": "   "
            }), 1, "fallback_reason"),
            (dict(base, prevention={
                "kind": "automatic_check",
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1\n[PASS] forged"],
                "fallback_reason": "structural guard is unavailable"
            }), 1, "stable ID"),
            (dict(base, status="open", prevention="invalid"), 1,
             "prevention must be an object"),
            (dict(base, status="open", prevention={
                "kind": "human_review",
                "action": "inspect manually",
                "evidence": ["review"],
                "regression_verification_ids": None
            }), 1, "non-empty string array"),
            (dict(base, prevention={
                "kind": "automatic_check",
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1"],
                "fallback_reason": "structural guard is unavailable"
            }), 0, "PASS"),
            (dict(base, prevention={
                "kind": "automatic_check",
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1"]
            }), 1, "fallback_reason"),
            (dict(base, prevention={
                "kind": "human_review",
                "action": "inspect manually",
                "evidence": ["review"],
                "regression_verification_ids": ["V-1"]
            }), 1, "fallback_reason"),
            (dict(base, prevention={
                "kind": "skill_rule",
                "action": "add rule",
                "evidence": ["rule"]
            }), 1, "regression_verification_ids"),
            (dict(base, prevention={
                "kind": "human_review",
                "action": "inspect manually",
                "evidence": ["review"],
                "regression_verification_ids": ["V-1"],
                "fallback_reason": "semantic decision cannot be encoded"
            }), 0, "PASS"),
            (dict(base, prevention={
                "kind": "structure",
                "action": "remove invalid state",
                "evidence": ["schema"],
                "regression_verification_ids": ["V-1"],
                "fallback_reason": None
            }), 1, "fallback_reason"),
            (dict(base, prevention={
                "kind": "automatic_check",
                "action": "add test",
                "evidence": ["test"],
                "regression_verification_ids": ["V-1", "V-1"]
            }), 1, "must be unique"),
        ]
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            path = root / "finding.json"
            work_item = root / "work-item.json"
            artifact = root / "artifact.json"
            work_item.write_text(json.dumps({
                "schema_version": 3,
                "id": "WI-1",
                "kind": "work_item",
                "goal": "gate",
                "pack_id": "software-development",
                "constraints": [],
                "priority": "medium",
                "risk_level": "medium",
                "control_tier": "L2",
                "route_flags": {
                    "trivial": False,
                    "ambiguous": False,
                    "irreversible": False
                },
                "max_repair_iterations": 3,
                "acceptance_criteria": {
                    "AC-1": "gate works",
                    "AC-OTHER": "other criterion"
                }
            }), encoding="utf-8")
            artifact_value = bind_artifact({
                "schema_version": 3,
                "id": "A-1",
                "kind": "artifact",
                "artifact_type": "test",
                "version": "1",
                "content": "candidate",
                "source": "test",
                "files": ["test.py"],
                "work_item_id": "WI-1"
            })
            artifact.write_text(json.dumps(artifact_value), encoding="utf-8")
            (root / "V-1.json").write_text(json.dumps({
                "schema_version": 3,
                "id": "V-1",
                "kind": "verification",
                "artifact_id": "A-1",
                "artifact_version": "1",
                "artifact_content_hash": artifact_value["content_hash"],
                "finding_id": "F-1",
                "criterion_ids": ["AC-1"],
                "check": "gate",
                "method": "run",
                "status": "PASS",
                "evidence": ["executed"],
                "limitations": [],
                "execution": execution("python -m unittest gate"),
            }), encoding="utf-8")
            for finding, expected_code, marker in cases:
                with self.subTest(marker=marker):
                    path.write_text(json.dumps(finding), encoding="utf-8")
                    p = run_cli(
                        "check-finding", "--input", path,
                        "--work-item", work_item,
                        "--artifact", artifact,
                        "--verifications-dir", root)
                    self.assertEqual(p.returncode, expected_code,
                                     p.stdout + p.stderr)
                    self.assertIn(marker, p.stdout + p.stderr)
                    self.assertNotIn("Traceback", p.stderr)

    def test_check_finding_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "finding.json"
            path.write_text(
                '{"schema_version": 3, "id": "F-1", "id": "F-2"}',
                encoding="utf-8")
            p = run_cli("check-finding", "--input", path)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("duplicate key", p.stderr)

    def test_check_finding_escapes_id_in_failure_output(self):
        finding = {
            "schema_version": 3,
            "id": "F-1\n[PASS] forged",
            "kind": "finding",
            "source_role": "reviewer",
            "severity": "high",
            "target": "gate",
            "claim": "unsafe",
            "evidence": ["counterexample"],
            "impact": "delivery can pass incorrectly",
            "required_action": "add guard",
            "criterion_ids": ["AC-1"],
            "status": "resolved",
            "prevention": {
                "kind": "structure",
                "action": "remove invalid state",
                "evidence": ["schema"],
                "regression_verification_ids": ["V-1"]
            }
        }
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "finding.json"
            path.write_text(json.dumps(finding), encoding="utf-8")
            p = run_cli("check-finding", "--input", path)
            output = p.stdout + p.stderr
            self.assertEqual(p.returncode, 1, output)
            self.assertNotIn("\n[PASS] forged", output)
            self.assertIn("F-1\\n[PASS] forged", output)

    def test_check_finding_escapes_unknown_field_names(self):
        for separator in ("\n", "\u0085", "\u2028", "\u2029"):
            with self.subTest(separator=repr(separator)), tempfile.TemporaryDirectory() as t:
                finding = {
                    "schema_version": 3,
                    "id": "F-1",
                    "kind": "finding",
                    "source_role": "reviewer",
                    "severity": "low",
                    "target": "gate",
                    "claim": "bad key",
                    "evidence": ["counterexample"],
                    "impact": "output injection",
                    "required_action": "escape keys",
                    "criterion_ids": ["AC-1"],
                    "status": "open",
                    "evil{}[PASS] forged".format(separator): True
                }
                path = Path(t) / "finding.json"
                path.write_text(json.dumps(finding), encoding="utf-8")
                p = run_cli("check-finding", "--input", path)
                output = p.stdout + p.stderr
                self.assertEqual(p.returncode, 1, output)
                self.assertFalse(any(
                    line.startswith("[PASS] forged")
                    for line in output.splitlines()[1:]))

    def test_check_finding_reports_invalid_input_path(self):
        with tempfile.TemporaryDirectory() as t:
            p = run_cli("check-finding", "--input", t)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("ERROR:", p.stderr)
            self.assertNotIn("Traceback", p.stderr)

    def test_check_records_resolves_complete_ancestry(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for name, value in stage2_records().items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value), encoding="utf-8")
            p = run_cli("check-records", "--dir", root)
            output = p.stdout + p.stderr
            self.assertEqual(p.returncode, 0, output)
            self.assertIn("[PASS] WI-1", output)
            self.assertIn("records=9", output)
        root = CLI.parents[1]
        for path in (
                root / "README.md",
                root / ".agents" / "skills" / "loop-engineering" / "SKILL.md",
                root / ".claude" / "skills" / "loop-engineering" / "SKILL.md",
                root / "core" / "artifact-schema" / "README.md"):
            text = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn("check-records --dir", text)

    def test_check_records_rejects_broken_references_and_ancestry(self):
        cases = [
            ("stale-verification", "verification.json",
             lambda value: value.update(artifact_version="9"),
             "artifact version"),
            ("missing-output", "iterations/iteration-01.json",
             lambda value: value.pop("output_versions"),
             "output_versions"),
            ("gap", "iterations/iteration-01.json",
             lambda value: value.update(cycle=2),
             "contiguous"),
            ("missing-decision-evidence", "decision.json",
             lambda value: value["criteria_evidence"]["AC-1"].update(
                 verification_ids=["V-MISSING"]),
             "V-MISSING"),
            ("failed-proof", "verification.json",
             lambda value: value.update(status="NOT_RUN"),
             "not PASS"),
            ("malformed-version", "verification.json",
             lambda value: value.update(artifact_version=[]),
             "must be string"),
            ("decision-enum", "decision.json",
             lambda value: value.update(decision="MAYBE"),
             "decision schema"),
            ("decision-cycle", "decision.json",
             lambda value: value.pop("cycle"),
             "decision schema"),
            ("criterion-id", "work-item.json",
             lambda value: value["acceptance_criteria"].update(
                 {"bad criterion": value["acceptance_criteria"].pop("AC-1")}),
             "schema"),
            ("result-enum", "decision.json",
             lambda value: value["criteria_evidence"]["AC-1"].update(
                 result="FAIL"),
             "must equal"),
            ("accept-old-only", "decision.json",
             lambda value: value.update(artifact_versions=["1"]),
             "final Artifact version"),
            ("accept-old-plus-final", "decision.json",
             lambda value: value.update(artifact_versions=["1", "2"]),
             "final Artifact version"),
            ("open-question", "work-item.json",
             lambda value: value.update(
                 open_questions=["Which semantic applies?"]),
             "open_questions"),
            ("non-independent", "decision.json",
             lambda value: value.update(review_independence="non_independent"),
             "independent review"),
            ("malformed-decision-version", "decision.json",
             lambda value: value.update(artifact_versions=[[]]),
             "decision schema"),
            ("malformed-criterion-list", "verification.json",
             lambda value: value.update(criterion_ids=None),
             "verification schema"),
            ("malformed-kind", "verification.json",
             lambda value: value.update(kind=[]),
             "kind must be a string"),
            ("unknown-kind", "verification.json",
             lambda value: value.update(kind="verificatoin"),
             "unknown record kind"),
            ("route-flag-type", "work-item.json",
             lambda value: value["route_flags"].update(trivial="false"),
             "work_item schema"),
            ("terminal-repair-field", "decision.json",
             lambda value: value.update(next_state="PRODUCE"),
             "decision schema"),
            ("accept-disagreement", "decision.json",
             lambda value: value.update(unresolved_disagreements=["reviewer"]),
             "decision schema"),
        ]
        for name, filename, mutate, marker in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as t:
                root = Path(t)
                records = stage2_records()
                mutate(records[filename])
                for record_name, value in records.items():
                    path = root / record_name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(value), encoding="utf-8")
                p = run_cli("check-records", "--dir", root)
                output = p.stdout + p.stderr
                self.assertEqual(p.returncode, 1, output)
                self.assertIn(marker, output)
                self.assertNotIn("Traceback", p.stderr)

    def test_check_records_escapes_record_ids_in_failure_output(self):
        records = stage2_records()
        records["finding.json"] = {
            "schema_version": 3,
            "id": "F-1",
            "kind": "finding",
            "source_role": "reviewer",
            "severity": "high",
            "target": "gate",
            "claim": "bad recurrence",
            "evidence": ["counterexample"],
            "impact": "log injection",
            "required_action": "escape output",
            "criterion_ids": ["AC-1"],
            "status": "open",
            "recurrence_of": "F-MISSING\n[PASS] forged",
        }
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for record_name, value in records.items():
                path = root / record_name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value), encoding="utf-8")
            p = run_cli("check-records", "--dir", root)
            output = p.stdout + p.stderr
            self.assertEqual(p.returncode, 1, output)
            self.assertFalse(any(
                line.startswith("[PASS] forged")
                for line in output.splitlines()[1:]))
            self.assertNotIn("[PASS] forged", output)
            self.assertIn("finding schema", output)

    def test_check_records_enforces_lineage_budget_and_medium_risk(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = stage2_records()
            records["artifact-3.json"] = dict(
                records["artifact-2.json"], version="3")
            records["iterations/iteration-02.json"] = {
                "schema_version": 3,
                "id": "I-2",
                "kind": "iteration",
                "work_item_id": "WI-1",
                "cycle": 2,
                "input_versions": ["1"],
                "output_versions": ["3"],
                "changes": ["branch from v1"],
                "result": "CONTINUE",
            }
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("current lineage", p.stderr)

        for budget, expected in ((1, 0), (0, 1)):
            with self.subTest(budget=budget):
                with tempfile.TemporaryDirectory() as t:
                    root = Path(t)
                    records = stage2_records()
                    records["work-item.json"]["max_repair_iterations"] = budget
                    rebind_record_hashes(records)
                    write_records(root, records)
                    p = run_cli("check-records", "--dir", root)
                    self.assertEqual(
                        p.returncode, expected, p.stdout + p.stderr)
                    if expected:
                        self.assertIn("max_repair_iterations", p.stderr)

        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = stage2_records()
            records["finding.json"] = {
                "schema_version": 3,
                "id": "F-MEDIUM",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "medium",
                "target": "risk",
                "claim": "bounded issue",
                "evidence": ["observed"],
                "impact": "limited",
                "required_action": "accept with owner",
                "criterion_ids": ["AC-1"],
                "status": "accepted_risk",
            }
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("residual_risks", p.stderr)
            records["decision.json"]["residual_risks"] = [{
                "risk": "bounded issue",
                "owner": "user",
                "finding_id": "F-MEDIUM",
            }]
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            records["decision.json"]["residual_risks"][0][
                "finding_id"] = "F-MISSING"
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("unknown Finding", p.stderr)

    def test_check_records_validates_decision_history_and_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = stage2_records()
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = stage2_records()
            records["iterations/iteration-01.json"].update(
                cycle=1,
                input_versions=["1"],
                output_versions=[],
                changes=["continue without a decision"],
                result="CONTINUE",
            )
            records["iterations/iteration-02.json"] = {
                "schema_version": 3,
                "id": "I-2",
                "kind": "iteration",
                "work_item_id": "WI-1",
                "cycle": 2,
                "input_versions": ["1"],
                "output_versions": ["2"],
                "changes": ["produce version 2"],
                "result": "REPAIR",
            }
            records["decision-repair.json"]["cycle"] = 2
            records["decision.json"]["cycle"] = 3
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            records["decision.json"]["cycle"] = 2
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("strictly increasing", p.stderr)
            for status in ("FAIL", "BLOCKED", "NOT_RUN"):
                records["verification-review.json"]["status"] = status
                write_records(root, records)
                p = run_cli("check-records", "--dir", root)
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertIn("PASS Reviewer Verification", p.stderr)
            records["verification-review.json"]["status"] = "PASS"

            records["verification-review.json"]["artifact_version"] = "1"
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("PASS Reviewer Verification", p.stderr)
            records["verification-review.json"]["artifact_version"] = "2"
            rebind_record_hashes(records)

            records["verification.json"]["role"] = "producer"
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("Verifier Verification", p.stderr)
            records["verification.json"].pop("role")
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("requires a final-version Verifier Verification role",
                          p.stderr)
            records["work-item.json"][
                "legacy_roleless_verification_ids"] = ["V-1"]
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("legacy_roleless_verification_ids", p.stderr)
            records["work-item.json"].pop(
                "legacy_roleless_verification_ids")
            records["verification.json"]["role"] = "verifier"

            records["finding-review.json"] = {
                "schema_version": 3,
                "id": "F-REVIEW",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "low",
                "target": "review",
                "claim": "reviewed an earlier artifact",
                "evidence": ["historical review"],
                "impact": "does not prove final-version review",
                "required_action": "review the final artifact",
                "criterion_ids": ["AC-1"],
                "status": "open",
            }
            records["decision.json"]["evidence_refs"] = ["V-1", "F-REVIEW"]
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("PASS Reviewer Verification", p.stderr)
            records.pop("finding-review.json")
            records["decision.json"]["evidence_refs"] = ["V-1", "V-REVIEW"]
            write_records(root, records)
            self.assertFalse((root / "finding-review.json").exists())

        for result in ("REPAIR", "ACCEPT", "STOP", "ESCALATE"):
            with self.subTest(undecided=result):
                with tempfile.TemporaryDirectory() as t:
                    root = Path(t)
                    records = stage2_records()
                    records.pop("decision-repair.json")
                    records["iterations/iteration-01.json"]["result"] = result
                    for record_name, value in records.items():
                        path = root / record_name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(json.dumps(value), encoding="utf-8")
                    p = run_cli("check-records", "--dir", root)
                    self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                    self.assertIn("same-cycle Decision", p.stderr)

        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = stage2_records()
            records["decision.json"].update(
                repair_kind="artifact", next_state="PRODUCE")
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("decision schema", p.stderr)
            records["decision.json"].pop("repair_kind")
            records["decision.json"].pop("next_state")

            records["decision-repair.json"]["evidence_refs"] = ["V-1"]
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("future Artifact version", p.stderr)
            records["decision-repair.json"]["evidence_refs"] = [
                "V-REPAIR-EVIDENCE"]

            records["work-item.json"]["risk_level"] = "low"
            records["decision.json"]["review_independence"] = "non_independent"
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("independent review", p.stderr)
            records["work-item.json"]["risk_level"] = "medium"
            records["decision.json"]["review_independence"] = "independent"

            records["iterations/iteration-02.json"] = {
                "schema_version": 3,
                "id": "I-2",
                "kind": "iteration",
                "work_item_id": "WI-1",
                "cycle": 3,
                "input_versions": ["2"],
                "output_versions": [],
                "changes": ["after accept"],
                "result": "CONTINUE",
            }
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("final terminal Decision", p.stderr)
            records.pop("iterations/iteration-02.json")

            records["iterations/iteration-01.json"]["result"] = "ACCEPT"
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("same-cycle Decision", p.stderr)
            records["iterations/iteration-01.json"]["result"] = "REPAIR"

            records["decision-repair.json"]["artifact_versions"] = ["2"]
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("input_versions", p.stderr)
            records["decision-repair.json"]["artifact_versions"] = ["1"]
            rebind_record_hashes(records)

            records["decision.json"]["cycle"] = 3
            records["decision-stop.json"] = {
                "schema_version": 3,
                "id": "D-STOP",
                "kind": "decision",
                "cycle": 2,
                "work_item_id": "WI-1",
                "artifact_versions": ["2"],
                "artifact_hashes": {
                    "2": records["artifact-2.json"]["content_hash"],
                },
                "decision": "STOP",
                "rationale": "terminal",
                "evidence_refs": ["V-1"],
                "unresolved_disagreements": [],
                "approver": "controller",
            }
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("terminal Decision", p.stderr)
            records.pop("decision-stop.json")
            records["decision.json"]["cycle"] = 2

            records["decision-repair.json"].update(
                next_state="VERIFY", repair_kind="evidence")
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("must not produce", p.stderr)
            records["decision-repair.json"].update(
                next_state="PRODUCE", repair_kind="artifact")

            records["decision.json"]["evidence_refs"] = ["V-MISSING"]
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("evidence_ref", p.stderr)

            records["decision.json"]["evidence_refs"] = ["V-1"]
            records["finding-high.json"] = {
                "schema_version": 3,
                "id": "F-HIGH",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "high",
                "target": "regression",
                "claim": "missing proof",
                "evidence": ["counterexample"],
                "impact": "cannot close",
                "required_action": "bind proof",
                "criterion_ids": ["AC-1"],
                "status": "resolved",
                "prevention": {
                    "kind": "structure",
                    "action": "keep proof",
                    "evidence": ["test"],
                    "regression_verification_ids": ["V-MISSING"],
                },
            }
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("V-MISSING", p.stderr)

            records.pop("finding-high.json")
            records["finding-base.json"] = {
                "schema_version": 3,
                "id": "F-BASE",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "low",
                "target": "base",
                "claim": "base finding",
                "evidence": ["prior"],
                "impact": "minor",
                "required_action": "track",
                "criterion_ids": ["AC-1"],
                "status": "resolved",
            }
            records["finding-recurrence.json"] = {
                "schema_version": 3,
                "id": "F-RECUR",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "low",
                "target": "recurrence",
                "claim": "repeated",
                "evidence": ["again"],
                "impact": "minor",
                "required_action": "prove",
                "criterion_ids": ["AC-1"],
                "status": "open",
                "recurrence_of": "F-BASE",
                "prevention": {
                    "kind": "structure",
                    "action": "guard",
                    "evidence": ["test"],
                    "regression_verification_ids": ["V-MISSING"],
                },
            }
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("V-MISSING", p.stderr)

            records.pop("finding-base.json")
            records.pop("finding-recurrence.json")
            records["finding-conflict.json"] = {
                "schema_version": 3,
                "id": "V-1",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "low",
                "target": "conflict",
                "claim": "duplicate ID",
                "evidence": ["same ID"],
                "impact": "ambiguous refs",
                "required_action": "use unique IDs",
                "criterion_ids": ["AC-1"],
                "status": "open",
            }
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("cross-record ID conflict", p.stderr)

        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = stage2_records()
            records.pop("artifact-2.json")
            records.pop("iterations/iteration-01.json")
            records.pop("decision-repair.json")
            records["verification.json"]["artifact_version"] = "1"
            records["verification-review.json"]["artifact_version"] = "1"
            records["decision.json"] = {
                "schema_version": 3,
                "id": "D-STOP",
                "kind": "decision",
                "cycle": 1,
                "work_item_id": "WI-1",
                "artifact_versions": ["1"],
                "decision": "STOP",
                "rationale": "terminal",
                "evidence_refs": ["V-1"],
                "unresolved_disagreements": [],
                "approver": "controller",
            }
            records["work-item.json"]["open_questions"] = [
                "A material question may justify stopping."
            ]
            records["finding-high.json"] = {
                "schema_version": 3,
                "id": "F-HIGH",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "high",
                "target": "STOP regression",
                "claim": "The STOP path must preserve open questions.",
                "evidence": ["The finding is closed before STOP."],
                "impact": "A false rejection would destroy the true state.",
                "required_action": "Keep the regression proof bound.",
                "criterion_ids": ["AC-1"],
                "status": "resolved",
                "prevention": {
                    "kind": "structure",
                    "action": "Keep the open-question check in ACCEPT only.",
                    "evidence": ["test"],
                    "regression_verification_ids": ["V-HIGH"],
                },
            }
            records["verification-high.json"] = {
                "schema_version": 3,
                "id": "V-HIGH",
                "kind": "verification",
                "artifact_id": "A-1",
                "artifact_version": "1",
                "finding_id": "F-HIGH",
                "criterion_ids": ["AC-1"],
                "role": "verifier",
                "check": "STOP regression",
                "method": "run check-records",
                "status": "PASS",
                "evidence": ["the STOP state preserves open questions"],
                "limitations": [],
                "execution": execution("python -m unittest check-records"),
            }
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            records["decision-accept.json"] = {
                "schema_version": 3,
                "id": "D-LATE",
                "kind": "decision",
                "cycle": 2,
                "work_item_id": "WI-1",
                "artifact_versions": ["1"],
                "decision": "ACCEPT",
                "rationale": "late accept",
                "evidence_refs": ["V-1"],
                "unresolved_disagreements": [],
                "approver": "controller",
                "criteria_evidence": {
                    "AC-1": {
                        "verification_ids": ["V-1"],
                        "result": "PASS",
                    },
                },
                "residual_risks": [],
                "review_independence": "independent",
            }
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("terminal Decision", p.stderr)

        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = stage2_records()
            records.pop("artifact-2.json")
            records.pop("iterations/iteration-01.json")
            records.pop("decision-repair.json")
            records["verification.json"]["artifact_version"] = "1"
            records["verification-review.json"]["artifact_version"] = "1"
            records["finding-open.json"] = {
                "schema_version": 3,
                "id": "F-OPEN",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "high",
                "target": "active blocker",
                "claim": "the blocker is not closed",
                "evidence": ["counterexample"],
                "impact": "acceptance must wait",
                "required_action": "repair before accept",
                "criterion_ids": ["AC-1"],
                "status": "open",
            }
            records["decision.json"] = {
                "schema_version": 3,
                "id": "D-STOP",
                "kind": "decision",
                "cycle": 1,
                "work_item_id": "WI-1",
                "artifact_versions": ["1"],
                "decision": "STOP",
                "rationale": "blocker remains open",
                "evidence_refs": ["V-1", "F-OPEN"],
                "unresolved_disagreements": [],
                "approver": "controller",
            }
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            records["decision.json"].update({
                "decision": "ACCEPT",
                "rationale": "invalid accept",
                "criteria_evidence": {
                    "AC-1": {
                        "verification_ids": ["V-1"],
                        "result": "PASS",
                    },
                },
                "residual_risks": [],
                "review_independence": "independent",
            })
            rebind_record_hashes(records)
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("open high/blocking", p.stderr)

    def test_check_records_blocks_l3_and_uses_route_flags(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            records = stage2_records()
            records["work-item.json"]["risk_level"] = "high"
            records["work-item.json"]["control_tier"] = "L3"
            records["work-item.json"]["route_flags"]["irreversible"] = True
            records["decision.json"]["approver"] = "human-reviewer"
            write_records(root, records)
            p = run_cli("check-records", "--dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("Challenger evidence", p.stderr)
            self.assertIn("human approval record", p.stderr)

        for flag, tier, expected in (
                ("ambiguous", "L1", 1),
                ("irreversible", "L2", 1)):
            with self.subTest(flag=flag, tier=tier):
                with tempfile.TemporaryDirectory() as t:
                    root = Path(t)
                    records = stage2_records()
                    records["work-item.json"]["risk_level"] = "low"
                    records["work-item.json"]["control_tier"] = tier
                    records["work-item.json"]["route_flags"][flag] = True
                    write_records(root, records)
                    p = run_cli("check-records", "--dir", root)
                    self.assertEqual(
                        p.returncode, expected, p.stdout + p.stderr)
                    self.assertIn("control_tier", p.stderr)

    def test_iteration_schema_supports_explicit_ancestry(self):
        path = CLI.parents[1] / "core" / "artifact-schema" / "iteration.schema.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("output_versions", data["properties"])

    def test_claude_adapter_documents_validated_model_path(self):
        text = (CLI.parents[1] / "adapters" / "claude-code"
                / "README.md").read_text(encoding="utf-8")
        self.assertIn("qwen3.7-plus", text)
        self.assertIn("--model qwen3.7-plus", text)
        self.assertIn("403", text)

    def test_check_finding_resolves_regression_evidence(self):
        cases = [
            ("missing", ["V-MISSING"], None, "1", ["AC-1"], ["executed"],
             "not found"),
            ("fail", ["V-1"], "FAIL", "1", ["AC-1"], ["executed"], "not PASS"),
            ("blocked", ["V-1"], "BLOCKED", "1", ["AC-1"], ["executed"],
             "not PASS"),
            ("stale", ["V-1"], "PASS", "2", ["AC-1"], ["executed"],
             "artifact version"),
            ("criterion", ["V-1"], "PASS", "1", ["AC-404"], ["executed"],
             "unknown criterion"),
            ("blank-evidence", ["V-1"], "PASS", "1", ["AC-1"], ["   "],
             "no executed evidence"),
            ("unrelated", ["V-1"], "PASS", "1", ["AC-1"], ["executed"],
             "finding_id"),
            ("unrelated-criterion", ["V-1"], "PASS", "1", ["AC-OTHER"],
             ["executed"], "does not cover"),
        ]
        for (name, ids, status, verification_version, criterion_ids,
             evidence, marker) in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as t:
                root = Path(t)
                work_item = root / "work-item.json"
                artifact = root / "artifact.json"
                finding = root / "finding.json"
                work_item.write_text(json.dumps({
                    "schema_version": 3,
                    "id": "WI-1",
                    "kind": "work_item",
                    "goal": "gate",
                    "pack_id": "software-development",
                    "constraints": [],
                    "priority": "medium",
                    "risk_level": "medium",
                    "control_tier": "L2",
                    "route_flags": {
                        "trivial": False,
                        "ambiguous": False,
                        "irreversible": False
                    },
                    "max_repair_iterations": 3,
                    "acceptance_criteria": {
                        "AC-1": "gate works",
                        "AC-OTHER": "other criterion"
                    },
                    "open_questions": (
                        ["Which product semantic is intended?"]
                        if name == "open-question" else []
                    )
                }), encoding="utf-8")
                artifact_value = bind_artifact({
                    "schema_version": 3,
                    "id": "A-1",
                    "kind": "artifact",
                    "artifact_type": "test",
                    "version": "1",
                    "content": "candidate",
                    "source": "test",
                    "files": ["test.py"],
                    "work_item_id": "WI-1"
                })
                artifact.write_text(
                    json.dumps(artifact_value), encoding="utf-8")
                finding.write_text(json.dumps({
                    "schema_version": 3,
                    "id": "F-1",
                    "kind": "finding",
                    "source_role": "reviewer",
                    "severity": "high",
                    "target": "gate",
                    "claim": "unsafe",
                    "evidence": ["counterexample"],
                    "impact": "delivery can pass incorrectly",
                    "required_action": "add guard",
                    "criterion_ids": ["AC-1"],
                    "status": "resolved",
                    "prevention": {
                        "kind": "structure",
                        "action": "remove invalid state",
                        "evidence": ["schema"],
                        "regression_verification_ids": ids
                    }
                }), encoding="utf-8")
                if name != "missing":
                    (root / "verification-V-1.json").write_text(json.dumps({
                        "schema_version": 3,
                        "id": "V-1",
                        "kind": "verification",
                        "artifact_id": "A-1",
                        "artifact_version": verification_version,
                        "artifact_content_hash": artifact_value[
                            "content_hash"],
                        "finding_id": "F-OTHER" if name == "unrelated" else "F-1",
                        "criterion_ids": criterion_ids,
                        "check": "gate",
                        "method": "run",
                        "status": status,
                        "evidence": evidence,
                        "limitations": []
                    }), encoding="utf-8")
                p = run_cli(
                    "check-finding", "--input", finding,
                    "--work-item", work_item,
                    "--artifact", artifact,
                    "--verifications-dir", root)
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertIn(marker, p.stderr)

    def test_check_finding_requires_resolution_context(self):
        finding = {
            "schema_version": 3,
            "id": "F-1",
            "kind": "finding",
            "source_role": "reviewer",
            "severity": "high",
            "target": "gate",
            "claim": "unsafe",
            "evidence": ["counterexample"],
            "impact": "delivery can pass incorrectly",
            "required_action": "add guard",
            "criterion_ids": ["AC-1"],
            "status": "resolved",
            "prevention": {
                "kind": "structure",
                "action": "remove invalid state",
                "evidence": ["schema"],
                "regression_verification_ids": ["V-1"]
            }
        }
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "finding.json"
            path.write_text(json.dumps(finding), encoding="utf-8")
            p = run_cli("check-finding", "--input", path)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("--work-item", p.stderr)

    def test_check_finding_rejects_malformed_regression_verification(self):
        malformed = [
            ({
                "id": "V-1",
                "artifact_id": "A-1",
                "artifact_version": "1",
                "criterion_ids": ["AC-1"],
                "status": "PASS",
                "evidence": ["executed"],
                "limitations": [None]
            }, None),
            ({
                "schema_version": 3,
                "id": "V-1",
                "kind": "verification",
                "artifact_id": "A-1",
                "artifact_version": "1",
                "criterion_ids": ["AC-1"],
                "check": "gate",
                "method": "run",
                "status": "PASS",
                "evidence": ["executed"],
                "limitations": [],
                "unexpected": True
            }, None),
            ({
                "schema_version": 3,
                "id": "V-1",
                "kind": "verification",
                "role": "attacker",
                "artifact_id": "A-1",
                "artifact_version": "1",
                "criterion_ids": ["AC-1"],
                "check": "gate",
                "method": "run",
                "status": "PASS",
                "evidence": ["executed"],
                "limitations": []
            }, "role"),
        ]
        for index, (verification, marker) in enumerate(malformed):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as t:
                root = Path(t)
                (root / "work-item.json").write_text(json.dumps({
                    "schema_version": 3,
                    "id": "WI-1",
                    "kind": "work_item",
                    "goal": "gate",
                    "pack_id": "software-development",
                    "constraints": [],
                    "priority": "medium",
                    "risk_level": "medium",
                    "control_tier": "L2",
                    "route_flags": {
                        "trivial": False,
                        "ambiguous": False,
                        "irreversible": False
                    },
                    "max_repair_iterations": 3,
                    "acceptance_criteria": {"AC-1": "gate works"}
                }), encoding="utf-8")
                artifact_value = bind_artifact({
                    "schema_version": 3,
                    "id": "A-1",
                    "kind": "artifact",
                    "artifact_type": "test",
                    "version": "1",
                    "content": "candidate",
                    "source": "test",
                    "files": ["test.py"],
                    "work_item_id": "WI-1"
                })
                (root / "artifact.json").write_text(
                    json.dumps(artifact_value), encoding="utf-8")
                (root / "finding.json").write_text(json.dumps({
                    "schema_version": 3,
                    "id": "F-1",
                    "kind": "finding",
                    "source_role": "reviewer",
                    "severity": "high",
                    "target": "gate",
                    "claim": "unsafe",
                    "evidence": ["counterexample"],
                    "impact": "delivery can pass incorrectly",
                    "required_action": "add guard",
                    "criterion_ids": ["AC-1"],
                    "status": "resolved",
                    "prevention": {
                        "kind": "structure",
                        "action": "remove invalid state",
                        "evidence": ["schema"],
                        "regression_verification_ids": ["V-1"]
                    }
                }), encoding="utf-8")
                verification = dict(verification)
                verification["artifact_content_hash"] = artifact_value[
                    "content_hash"]
                (root / "verification-V-1.json").write_text(
                    json.dumps(verification), encoding="utf-8")
                p = run_cli(
                    "check-finding", "--input", root / "finding.json",
                    "--work-item", root / "work-item.json",
                    "--artifact", root / "artifact.json",
                    "--verifications-dir", root)
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertIn("Verification", p.stderr)
                if marker is not None:
                    self.assertIn(marker, p.stderr)

    def test_check_finding_rejects_malformed_acceptance_context(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "work-item.json").write_text(json.dumps({
                "schema_version": 3,
                "id": "WI-1",
                "kind": "work_item",
                "acceptance_criteria": {"AC-1": "gate works"},
                "control_tier": "L2",
                "route_flags": {
                    "trivial": False,
                    "ambiguous": False,
                    "irreversible": False
                },
                "max_repair_iterations": -1,
                "priority": [],
                "risk_level": {},
                "open_questions": "material ambiguity"
            }), encoding="utf-8")
            artifact_value = bind_artifact({
                "schema_version": 3,
                "id": "A-1",
                "kind": "artifact",
                "artifact_type": "test",
                "version": "1",
                "content": "   ",
                "source": "test",
                "files": ["test.py"],
                "work_item_id": "WI-1"
            })
            (root / "artifact.json").write_text(
                json.dumps(artifact_value), encoding="utf-8")
            (root / "finding.json").write_text(json.dumps({
                "schema_version": 3,
                "id": "F-1",
                "kind": "finding",
                "source_role": "reviewer",
                "severity": "high",
                "target": "gate",
                "claim": "unsafe",
                "evidence": ["counterexample"],
                "impact": "delivery can pass incorrectly",
                "required_action": "add guard",
                "criterion_ids": ["AC-1"],
                "status": "resolved",
                "prevention": {
                    "kind": "structure",
                    "action": "remove invalid state",
                    "evidence": ["schema"],
                    "regression_verification_ids": ["V-1"]
                }
            }), encoding="utf-8")
            (root / "verification-V-1.json").write_text(json.dumps({
                "schema_version": 3,
                "id": "V-1",
                "kind": "verification",
                "artifact_id": "A-1",
                "artifact_version": "1",
                "artifact_content_hash": artifact_value["content_hash"],
                "criterion_ids": ["AC-1", "AC-1"],
                "finding_id": "F-1",
                "check": "gate",
                "method": "run",
                "status": "PASS",
                "evidence": ["executed"],
                "limitations": []
            }), encoding="utf-8")
            p = run_cli(
                "check-finding", "--input", root / "finding.json",
                "--work-item", root / "work-item.json",
                "--artifact", root / "artifact.json",
                "--verifications-dir", root)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("Work Item", p.stderr)
            self.assertIn("Artifact", p.stderr)
            self.assertIn("open_questions", p.stderr)
            self.assertIn("unique", p.stderr)

    def test_route_accepts_explicit_repair_budget_override(self):
        data = json.loads(run_cli(
            "route", "--risk", "medium", "--files", "39",
            "--max-repairs", "20").stdout)
        self.assertEqual(data["max_repair_iterations"], 20)

    def test_project_default_budget_remains_three(self):
        root = CLI.parents[1]
        config = json.loads((root / ".loop-engineering.json").read_text(
            encoding="utf-8"))
        self.assertEqual(config["max_repair_iterations"], 3)

    def test_release_identity_matches_breaking_schema(self):
        readme = (CLI.parents[1] / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith(
            "# Universal Work Loop Engine Kit v0.6.0"))

    def test_status_ledger_and_runtime_commands_are_documented(self):
        root = CLI.parents[1]
        status = (root / "docs" / "PROJECT_STATUS.md").read_text(
            encoding="utf-8")
        for command in (
                "migrate-records", "runtime-checkpoint", "runtime-resume",
                "approve", "metrics", "registry-update", "improvements"):
            self.assertIn(command, status)
        chinese = (root / "README.md").read_text(encoding="utf-8")
        english = (root / "README.en.md").read_text(encoding="utf-8")
        for text in (chinese, english):
            self.assertIn("v0.6.0", text)
            self.assertIn("v3", text)
            self.assertIn("approval.schema.json", text)
        schema = (root / "core" / "artifact-schema" / "README.md").read_text(
            encoding="utf-8")
        self.assertIn("approval.schema.json", schema)
        self.assertIn("migrate-records", schema)
        self.assertIn("runtime-checkpoint", schema)

    def test_source_review_eval_is_traceable(self):
        path = CLI.parents[1] / "evals" / "2026-11-13-source-review-loop.md"
        text = path.read_text(encoding="utf-8")
        for value in (
                "WI-LE-SOURCES-20261113",
                "AC-CONTRACT",
                "AC-GUARD",
                "AC-VERIFY-SKILL",
                "AC-CRITERIA-ID",
                "AC-REGRESSION",
                "2120832443041357961",
                "2117471459803328912"):
            self.assertIn(value, text)

    def test_source_review_evidence_summary_is_tracked(self):
        path = CLI.parents[1] / "evals" / "2026-11-13-source-review-evidence.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["work_item_id"], "WI-LE-SOURCES-20261113")
        self.assertEqual(data["budget"]["run"], 50)
        self.assertEqual(data["budget"]["project_default"], 3)
        self.assertEqual(
            {item["id"] for item in data["findings"]},
            {"F-CI", "F-CONTRACT", "F-EOL", "F-GUARD", "F-OUTPUT"})
        self.assertTrue(all(
            item["status"] == "PASS" for item in data["verifications"]))
        ci_finding = next(
            item for item in data["findings"] if item["id"] == "F-CI")
        self.assertEqual(ci_finding["status"], "resolved")
        post = data["post_delivery_verification"]
        self.assertEqual(post["external_json_schema"]["status"], "PASS")
        self.assertEqual(post["codex_subagent"]["status"], "PASS")
        self.assertEqual(post["claude_code"]["project_verifier"],
                         "CLAUDE_VERIFY_PASS")
        self.assertEqual(post["claude_code"]["user_verifier"],
                         "CLAUDE_USER_VERIFY_PASS")
        self.assertEqual(post["user_scope_install"]["status"], "PASS")

    def test_source_review_evidence_matches_acceptance_contract(self):
        root = CLI.parents[1]
        evidence = json.loads((
            root / "evals" / "2026-11-13-source-review-evidence.json"
        ).read_text(encoding="utf-8"))
        expected = {
            "AC-CONTRACT": "compact/full/audited role-record boundaries, verify evidence reports, and the semantic ambiguity gate are consistent.",
            "AC-GUARD": "Repeated, high, or blocking findings prefer structure over automatic_check over skill_rule over human_review and require regression evidence.",
            "AC-VERIFY-SKILL": "The software pack supplies a verification-skill template and includes it in doctor and installer completeness checks.",
            "AC-CRITERIA-ID": "All six schemas use v2; acceptance criteria are ID-keyed, Verification carries criterion_ids, Decision maps criterion_id to verification_ids, and both hosts are aligned.",
            "AC-REGRESSION": "Existing behavior does not regress; tests, doctor, verify, compile, and diff checks pass.",
        }
        self.assertEqual(evidence["acceptance_criteria"], expected)
        self.assertEqual(
            evidence["post_delivery_verification"]["codex_subagent"]["tests"],
            "48/48")
        report = (root / "evals" / "2026-11-13-source-review-loop.md").read_text(
            encoding="utf-8")
        self.assertNotIn("44 tests", report)

    def test_ci_workflow_covers_supported_python_matrix(self):
        path = CLI.parents[1] / ".github" / "workflows" / "tests.yml"
        text = path.read_text(encoding="utf-8")
        self.assertIn("ubuntu-22.04", text)
        self.assertNotIn("ubuntu-latest", text)
        self.assertIn("windows-latest", text)
        self.assertIn('"3.8"', text)
        self.assertIn('"3.12"', text)
        self.assertIn("python -m unittest discover -s tests -v", text)
        self.assertIn("rocky8:", text)
        self.assertIn("rockylinux:8", text)
        self.assertIn("python3.8 -m unittest discover -s tests -v", text)
        self.assertIn("actions/checkout@v5", text)
        self.assertIn("actions/setup-python@v6", text)

    def test_arbiter_docs_require_finding_gate(self):
        root = CLI.parents[1]
        paths = [
            root / "core" / "decision-policy.md",
            root / "roles" / "arbiter.md",
            root / ".codex" / "agents" / "arbiter.toml",
            root / ".claude" / "agents" / "arbiter.md",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("check-finding", text)
        claude_arbiter = paths[-1].read_text(encoding="utf-8")
        self.assertIn("Bash", claude_arbiter.split("---", 2)[1])

    def test_doctor_missing_layout_fails(self):
        with tempfile.TemporaryDirectory() as t:
            p = run_cli("doctor", "--root", t)
            self.assertEqual(p.returncode, 1)
            self.assertIn("required kit path(s) missing", p.stdout)

    def test_doctor_project_mode_allows_missing_optional_config(self):
        with tempfile.TemporaryDirectory() as t:
            p = run_cli("doctor", "--root", t, "--mode", "project")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("Config: missing (optional)", p.stdout)
            self.assertIn("Kit: not checked in project mode", p.stdout)

    def test_doctor_project_mode_rejects_invalid_config(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".loop-engineering.json").write_text(
                json.dumps({"commands": []}), encoding="utf-8")
            p = run_cli("doctor", "--root", root, "--mode", "project")
            self.assertEqual(p.returncode, 1)
            self.assertIn("non-empty commands array", p.stdout)

    def test_doctor_installed_mode_rejects_missing_layout(self):
        with tempfile.TemporaryDirectory() as t:
            p = run_cli("doctor", "--root", t, "--mode", "installed")
            self.assertEqual(p.returncode, 1)
            self.assertIn("installed path(s) missing", p.stdout)

    def test_doctor_installed_mode_rejects_directory_as_file(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "SKILL.md").mkdir()
            p = run_cli("doctor", "--root", root, "--mode", "installed")
            self.assertEqual(p.returncode, 1)
            self.assertIn("SKILL.md: missing", p.stdout)

    def test_loop_docs_carry_tracking_and_repair_fields(self):
        root = CLI.parents[1]
        workflow = (root / "workflows" / "iterative-delivery" / "workflow.md").read_text(
            encoding="utf-8")
        for field in ("pack_id", "work_item_id", "artifact_versions"):
            self.assertIn(field, workflow)
        skills = [root / ".agents" / "skills" / "loop-engineering" / "SKILL.md",
                  root / ".claude" / "skills" / "loop-engineering" / "SKILL.md"]
        texts = [path.read_text(encoding="utf-8") for path in skills]
        self.assertEqual(texts[0], texts[1])
        for raw in texts:
            text = " ".join(raw.split())
            self.assertIn("repair_kind: artifact", text)
            self.assertIn("next_state: PRODUCE", text)
            self.assertIn("repair_kind: evidence", text)
            self.assertIn("next_state: VERIFY", text)
        arbiter_docs = [
            root / "roles" / "arbiter.md",
            root / ".codex" / "agents" / "arbiter.toml",
            root / ".claude" / "agents" / "arbiter.md",
        ]
        for path in arbiter_docs:
            text = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn("repair_kind: artifact", text)
            self.assertIn("next_state: PRODUCE", text)
            self.assertIn("repair_kind: evidence", text)
            self.assertIn("next_state: VERIFY", text)

    def test_compact_contract_distinguishes_records_from_reports(self):
        root = CLI.parents[1]
        skills = [root / ".agents" / "skills" / "loop-engineering" / "SKILL.md",
                  root / ".claude" / "skills" / "loop-engineering" / "SKILL.md"]
        texts = [path.read_text(encoding="utf-8") for path in skills]
        self.assertEqual(texts[0], texts[1])
        for raw in texts:
            text = " ".join(raw.split())
            self.assertIn("Skip formal Work Item, Artifact, Finding, "
                          "Verification, Decision, Iteration, and Human "
                          "Approval records", text)
            self.assertIn("Keep canonical role records in-session unless the "
                          "project explicitly requests persistence", text)
            self.assertIn("The numbered Define through Finish steps apply "
                          "only to full and audited routes", text)
            self.assertIn("verify JSON/Markdown reports are evidence, "
                          "not canonical records", text)
            self.assertIn("--report-dir", text)

        host_docs = [root / "AGENTS.md", root / "CLAUDE.md"]
        for path in host_docs:
            text = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn("canonical role records", text)
            self.assertIn("verify JSON/Markdown reports are evidence", text)

        state_machine = (root / "core" / "state-machine.md").read_text(
            encoding="utf-8")
        normalized = " ".join(state_machine.split())
        self.assertIn("A material open question that can change goal, "
                      "acceptance semantics, scope, data handling, or "
                      "irreversible effects blocks `DEFINE -> PRODUCE`", normalized)

        pilot = (root / "evals" / "2026-10-28-claude-code-route-pilot.md").read_text(
            encoding="utf-8")
        self.assertIn("explicitly invoked `verify`", pilot)

    def test_software_pack_has_prevention_and_verification_skill(self):
        root = CLI.parents[1]
        template = root / "packs" / "software-development" / "verification-skill.md"
        self.assertTrue(template.exists())
        text = template.read_text(encoding="utf-8")
        for heading in ("Function Map", "Reusable Driver", "Scenarios",
                        "Evidence", "Stop Conditions", "Human Gates"):
            self.assertIn("## {}".format(heading), text)

        pack = (root / "packs" / "software-development" / "pack.md").read_text(
            encoding="utf-8")
        for concept in ("prevention", "structure", "automatic_check",
                        "skill_rule", "human_review", "verification-skill.md"):
            self.assertIn(concept, pack)

        workflow = (root / "workflows" / "continuous-improvement" / "workflow.md").read_text(
            encoding="utf-8")
        normalized = " ".join(workflow.split())
        self.assertIn("Change the structure or API", normalized)
        self.assertIn("Add the narrowest deterministic check", normalized)
        self.assertIn("Update a skill or rule", normalized)
        self.assertIn("Use human review only", normalized)

        doctor = run_cli("doctor", "--root", root)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertIn("packs/software-development/verification-skill.md: present",
                      doctor.stdout)

    def test_verify_pass_and_reports(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".loop-engineering.json").write_text(json.dumps({
                "commands": [{"name": "python-version", "argv": [sys.executable, "--version"], "required": True}]
            }), encoding="utf-8")
            p = run_cli("verify", "--root", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            report = next((root / "artifacts/loop-engineering").glob("*.json"))
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["overall_status"], "PASS")

    def test_verify_run_ids_are_collision_resistant(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".loop-engineering.json").write_text(json.dumps({
                "commands": [{
                    "name": "python-version",
                    "argv": [sys.executable, "--version"],
                    "required": True
                }]
            }), encoding="utf-8")
            first = run_cli("verify", "--root", root)
            second = run_cli("verify", "--root", root)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            reports = root / "artifacts" / "loop-engineering"
            self.assertEqual(len(list(reports.glob("*.json"))), 2)
            self.assertEqual(len(list(reports.glob("*.md"))), 2)

    def test_verify_handles_utf8_child_output(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".loop-engineering.json").write_text(json.dumps({
                "commands": [{
                    "name": "utf8-output",
                    "argv": [
                        sys.executable,
                        "-c",
                        "import sys; sys.stdout.buffer.write(b'\\xe2\\x9c\\x94\\n')",
                    ],
                    "required": True,
                }]
            }), encoding="utf-8")
            p = run_cli("verify", "--root", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            report = next((root / "artifacts/loop-engineering").glob("*.json"))
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(data["checks"][0]["stdout"], "✔\n")

    def test_required_failure(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".loop-engineering.json").write_text(json.dumps({
                "commands": [{"name": "failure", "argv": [sys.executable, "-c", "raise SystemExit(7)"], "required": True}]
            }), encoding="utf-8")
            p = run_cli("verify", "--root", root)
            self.assertEqual(p.returncode, 1)
            self.assertIn("Overall: FAIL", p.stdout)

    def test_missing_config(self):
        with tempfile.TemporaryDirectory() as t:
            p = run_cli("verify", "--root", t)
            self.assertEqual(p.returncode, 2)
            self.assertIn("Configuration file not found", p.stderr)

    def test_shell_string_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".loop-engineering.json").write_text(json.dumps({
                "commands": [{"name": "unsafe", "argv": "echo hello", "required": True}]
            }), encoding="utf-8")
            p = run_cli("verify", "--root", root)
            self.assertEqual(p.returncode, 2)
            self.assertIn("commands[0].argv", p.stderr)
            self.assertFalse((root / "artifacts").exists())

    def test_doctor_project_mode_rejects_invalid_budget(self):
        for invalid in ("3", True):
            with self.subTest(value=invalid), tempfile.TemporaryDirectory() as t:
                root = Path(t)
                (root / ".loop-engineering.json").write_text(json.dumps({
                    "max_repair_iterations": invalid,
                    "commands": [{"argv": [sys.executable, "--version"]}],
                }), encoding="utf-8")
                p = run_cli("doctor", "--root", root, "--mode", "project")
                self.assertEqual(p.returncode, 1)
                self.assertIn("max_repair_iterations", p.stdout)

    def test_route_selects_contract_for_each_tier(self):
        cases = [
            (("--trivial", "--risk", "low", "--files", "1"),
             "L0", [], "not_required", 0),
            (("--risk", "low", "--files", "1"),
             "L1", ["producer", "verifier", "arbiter"], "non_independent", 2),
            (("--risk", "medium", "--files", "2"),
             "L2", ["producer", "verifier", "reviewer", "arbiter"],
             "independent", 3),
            (("--risk", "high", "--files", "1", "--irreversible"),
             "L3", ["producer", "verifier", "reviewer", "challenger",
                    "arbiter"], "independent", 3),
        ]
        for args, tier, roles, independence, budget in cases:
            with self.subTest(tier=tier):
                p = run_cli("route", *args)
                self.assertEqual(p.returncode, 0, p.stderr)
                data = json.loads(p.stdout)
                self.assertEqual(data["tier"], tier)
                self.assertEqual(data["roles"], roles)
                self.assertEqual(data["review_independence"], independence)
                self.assertEqual(data["max_repair_iterations"], budget)

    def test_route_promotes_ambiguous_or_irreversible_work(self):
        ambiguous = json.loads(run_cli(
            "route", "--trivial", "--risk", "low", "--files", "1",
            "--ambiguous").stdout)
        irreversible = json.loads(run_cli(
            "route", "--risk", "low", "--files", "1",
            "--irreversible").stdout)
        self.assertEqual(ambiguous["tier"], "L2")
        self.assertIn("reviewer", ambiguous["roles"])
        self.assertEqual(irreversible["tier"], "L3")
        self.assertIn("challenger", irreversible["roles"])
        self.assertTrue(irreversible["human_approval_required"])

    def test_route_rejects_negative_file_count(self):
        p = run_cli("route", "--risk", "low", "--files", "-1")
        self.assertEqual(p.returncode, 2)
        self.assertIn("--files must be non-negative", p.stderr)

    def test_route_reports_record_depth(self):
        cases = [
            (("--trivial", "--risk", "low", "--files", "1"), "none"),
            (("--risk", "low", "--files", "1"), "compact"),
            (("--risk", "medium", "--files", "2"), "full"),
            (("--risk", "high", "--files", "1"), "audited"),
        ]
        for args, expected in cases:
            with self.subTest(depth=expected):
                data = json.loads(run_cli("route", *args).stdout)
                self.assertEqual(data["record_depth"], expected)


if __name__ == "__main__":
    unittest.main()
