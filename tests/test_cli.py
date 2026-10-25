import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / "loop_engineering" / "cli.py"


def run_cli(*args):
    return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class CliTests(unittest.TestCase):
    def test_doctor(self):
        p = run_cli("doctor", "--root", CLI.parents[1])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Python:", p.stdout)
        self.assertIn("core/protocol.md: present", p.stdout)
        self.assertIn("roles/challenger.md: present", p.stdout)
        self.assertIn("packs/architecture-design/pack.md: present", p.stdout)

    def test_artifact_schemas_are_valid_json(self):
        schema_root = CLI.parents[1] / "core" / "artifact-schema"
        expected = {
            "work-item.schema.json",
            "artifact.schema.json",
            "finding.schema.json",
            "verification.schema.json",
            "decision.schema.json",
            "iteration.schema.json",
        }
        self.assertEqual({p.name for p in schema_root.glob("*.schema.json")}, expected)
        for path in schema_root.glob("*.schema.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(data["type"], "object")

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
        self.assertEqual(data["properties"]["criteria_evidence"]["minItems"], 1)
        self.assertIn("residual_risks", accept_rule["then"]["required"])
        self.assertIn("review_independence", accept_rule["then"]["required"])
        self.assertIn("next_state", repair_rule["then"]["required"])
        self.assertIn("repair_kind", repair_rule["then"]["required"])
        criteria = data["properties"]["criteria_evidence"]["items"]
        self.assertEqual(criteria["properties"]["result"]["const"], "PASS")
        self.assertEqual(accept_rule["then"]["properties"]["unresolved_disagreements"]["maxItems"], 0)

    def test_high_findings_cannot_be_accepted_risk(self):
        path = CLI.parents[1] / "core" / "artifact-schema" / "finding.schema.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        rule = data["allOf"][0]
        self.assertIn("high", rule["if"]["properties"]["severity"]["enum"])
        self.assertNotIn("accepted_risk", rule["then"]["properties"]["status"]["enum"])

    def test_verification_schema_links_artifact_version(self):
        path = CLI.parents[1] / "core" / "artifact-schema" / "verification.schema.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("artifact_id", data["required"])
        self.assertIn("artifact_version", data["required"])

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


if __name__ == "__main__":
    unittest.main()
