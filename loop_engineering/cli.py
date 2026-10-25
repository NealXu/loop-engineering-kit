#!/usr/bin/env python3
"""Cross-platform standard-library CLI for deterministic verification."""
import argparse
import datetime
import json
from pathlib import Path
import platform
import subprocess
import sys
import time


def load_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError("Configuration file not found: {}".format(path))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON: {}".format(exc))
    if not isinstance(value, dict):
        raise ValueError("Configuration root must be a JSON object")
    return value


def load_verify_config(path):
    config = load_json(path)
    commands = config.get("commands")
    if not isinstance(commands, list) or not commands:
        raise ValueError("config must contain a non-empty commands array")
    for index, spec in enumerate(commands):
        if not isinstance(spec, dict):
            raise ValueError("commands[{}] must be an object".format(index))
        argv = spec.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            raise ValueError("commands[{}].argv must be a non-empty array of strings".format(index))
        if "required" in spec and not isinstance(spec["required"], bool):
            raise ValueError("commands[{}].required must be a boolean".format(index))
        if "name" in spec and not isinstance(spec["name"], str):
            raise ValueError("commands[{}].name must be a string".format(index))
    maximum = config.get("max_repair_iterations", 3)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0:
        raise ValueError("max_repair_iterations must be a non-negative integer")
    return config


def doctor(root, mode="kit"):
    root = Path(root).resolve()
    print("Loop Engineering Kit doctor")
    print("Mode: {}".format(mode))
    print("Python: {}".format(sys.version.split()[0]))
    print("Platform: {}".format(platform.platform()))
    print("Root: {}".format(root))
    if not root.is_dir():
        print("ERROR: root directory does not exist")
        return 2
    if mode == "project":
        config_path = root / ".loop-engineering.json"
        if not config_path.exists():
            print("Config: missing (optional)")
        else:
            try:
                load_verify_config(config_path)
            except ValueError as exc:
                print("ERROR: {}".format(exc))
                return 1
            print("Config: valid")
        for name in ("AGENTS.md", "CLAUDE.md"):
            print("{}: {} (optional)".format(
                name, "present" if (root / name).exists() else "missing"))
        print("Kit: not checked in project mode")
        return 0
    config_present = (root / ".loop-engineering.json").exists()
    print("Config: {}".format("present" if config_present else "missing"))
    if config_present:
        try:
            load_verify_config(root / ".loop-engineering.json")
        except ValueError as exc:
            print("ERROR: {}".format(exc))
            return 1
        print("Config validation: PASS")
    missing = [] if config_present else [".loop-engineering.json"]
    for name in (
        "AGENTS.md",
        "CLAUDE.md",
        "core/protocol.md",
        "core/state-machine.md",
        "core/decision-policy.md",
        "core/artifact-schema/work-item.schema.json",
        "core/artifact-schema/artifact.schema.json",
        "core/artifact-schema/finding.schema.json",
        "core/artifact-schema/verification.schema.json",
        "core/artifact-schema/decision.schema.json",
        "core/artifact-schema/iteration.schema.json",
        "core/artifact-schema/README.md",
        "roles/producer.md",
        "roles/verifier.md",
        "roles/reviewer.md",
        "roles/challenger.md",
        "roles/arbiter.md",
        "workflows/iterative-delivery/workflow.md",
        "workflows/adversarial-review/workflow.md",
        "workflows/continuous-improvement/workflow.md",
        "packs/software-development/pack.md",
        "packs/architecture-design/pack.md",
        ".agents/skills/loop-engineering/SKILL.md",
        ".claude/skills/loop-engineering/SKILL.md",
        ".codex/agents/producer.toml",
        ".codex/agents/verifier.toml",
        ".codex/agents/reviewer.toml",
        ".codex/agents/challenger.toml",
        ".codex/agents/arbiter.toml",
        ".claude/agents/producer.md",
        ".claude/agents/verifier.md",
        ".claude/agents/reviewer.md",
        ".claude/agents/challenger.md",
        ".claude/agents/arbiter.md",
        "adapters/codex/README.md",
        "adapters/claude-code/README.md",
    ):
        present = (root / name).exists()
        print("{}: {}".format(name, "present" if present else "missing"))
        if not present:
            missing.append(name)
    if missing:
        print("ERROR: {} required kit path(s) missing".format(len(missing)))
        return 1
    if sys.version_info < (3, 8):
        print("WARNING: Python 3.8+ recommended")
    return 0


def run_one(spec, root, timeout):
    name = str(spec.get("name", "unnamed-check"))
    argv = spec.get("argv")
    required = bool(spec.get("required", True))
    base = {"name": name, "argv": argv, "required": required, "duration_seconds": 0.0}
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        return dict(base, status="FAIL", exit_code=None, stdout="", stderr="argv must be a non-empty array of strings")
    # Portable interpreter token: use the Python executable running this CLI.
    argv = [sys.executable if item == "{python}" else item for item in argv]
    base["argv"] = argv
    started = time.monotonic()
    try:
        p = subprocess.run(argv, cwd=str(root), shell=False, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, check=False)
        return dict(base, status="PASS" if p.returncode == 0 else "FAIL",
                    exit_code=p.returncode, duration_seconds=round(time.monotonic()-started, 3),
                    stdout=p.stdout[-12000:], stderr=p.stderr[-12000:])
    except subprocess.TimeoutExpired:
        return dict(base, status="FAIL", exit_code=None,
                    duration_seconds=round(time.monotonic()-started, 3),
                    stdout="", stderr="Timed out after {} seconds".format(timeout))
    except OSError as exc:
        return dict(base, status="BLOCKED", exit_code=None,
                    duration_seconds=round(time.monotonic()-started, 3), stdout="", stderr=str(exc))


def markdown(data):
    lines = ["# Loop Engineering Verification Report", "",
             "- Run ID: `{}`".format(data["run_id"]),
             "- Root: `{}`".format(data["root"]),
             "- Overall: **{}**".format(data["overall_status"]), "",
             "| Check | Required | Status | Exit | Seconds |",
             "|---|---:|---|---:|---:|"]
    for c in data["checks"]:
        lines.append("| {} | {} | {} | {} | {} |".format(
            c["name"], "yes" if c["required"] else "no", c["status"],
            c["exit_code"], c["duration_seconds"]))
    for c in data["checks"]:
        lines.extend(["", "## {}".format(c["name"]), "",
                      "- Command: `{}`".format(" ".join(c["argv"] or [])),
                      "- Status: {}".format(c["status"])])
        if c["stdout"]:
            lines.extend(["", "Stdout:", "```text", c["stdout"].rstrip(), "```"])
        if c["stderr"]:
            lines.extend(["", "Stderr:", "```text", c["stderr"].rstrip(), "```"])
    lines.extend(["", "This report records local command outcomes; it does not replace independent code review.", ""])
    return "\n".join(lines)


def verify(root, config_path, report_dir, timeout):
    root = Path(root).resolve()
    config_path = Path(config_path).resolve() if config_path else root / ".loop-engineering.json"
    try:
        config = load_verify_config(config_path)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    commands = config["commands"]
    maximum = config.get("max_repair_iterations", 3)
    started = datetime.datetime.now().astimezone()
    checks = [run_one(x if isinstance(x, dict) else {}, root, timeout) for x in commands]
    failed = [x for x in checks if x["required"] and x["status"] != "PASS"]
    data = {"schema_version": 1, "run_id": started.strftime("%Y%m%d-%H%M%S-%z"),
            "root": str(root), "started_at": started.isoformat(),
            "overall_status": "FAIL" if failed else "PASS",
            "max_repair_iterations": maximum, "checks": checks,
            "required_failure_count": len(failed)}
    out = Path(report_dir).resolve() if report_dir else root / "artifacts" / "loop-engineering"
    out.mkdir(parents=True, exist_ok=True)
    jp = out / ("verify-{}.json".format(data["run_id"]))
    mp = out / ("verify-{}.md".format(data["run_id"]))
    jp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mp.write_text(markdown(data), encoding="utf-8")
    print("Overall: {}".format(data["overall_status"]))
    for c in checks:
        print("[{}] {} required={} exit={}".format(c["status"], c["name"], c["required"], c["exit_code"]))
    print("JSON report: {}".format(jp))
    print("Markdown report: {}".format(mp))
    return 1 if failed else 0


def main():
    p = argparse.ArgumentParser(description="Loop Engineering helper")
    subs = p.add_subparsers(dest="command", required=True)
    d = subs.add_parser("doctor")
    d.add_argument("--root", default=".")
    d.add_argument("--mode", choices=("kit", "project"), default="kit")
    v = subs.add_parser("verify")
    v.add_argument("--root", default=".")
    v.add_argument("--config", default=None)
    v.add_argument("--report-dir", default=None)
    v.add_argument("--timeout", type=int, default=900)
    r = subs.add_parser("report")
    r.add_argument("--input", required=True)
    r.add_argument("--format", choices=("markdown", "json"), default="markdown")
    a = p.parse_args()
    if a.command == "doctor":
        return doctor(a.root, a.mode)
    if a.command == "verify":
        if a.timeout <= 0:
            p.error("--timeout must be positive")
        return verify(a.root, a.config, a.report_dir, a.timeout)
    try:
        data = load_json(a.input)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, ensure_ascii=False) if a.format == "json" else markdown(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
