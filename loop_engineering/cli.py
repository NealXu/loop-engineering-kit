#!/usr/bin/env python3
"""Cross-platform standard-library CLI for deterministic verification."""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid


STABLE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "core" / "artifact-schema"
MIGRATION_MANIFEST = SCHEMA_ROOT / "migrations" / "v2-to-v3.json"
SCHEMA_FILES = {
    "work_item": "work-item.schema.json",
    "artifact": "artifact.schema.json",
    "finding": "finding.schema.json",
    "verification": "verification.schema.json",
    "decision": "decision.schema.json",
    "iteration": "iteration.schema.json",
    "approval": "approval.schema.json",
}


def _quoted_names(items):
    return ", ".join(json.dumps(item, ensure_ascii=True) for item in items)


def _unique_object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(
                "duplicate key: {}".format(json.dumps(key, ensure_ascii=True)))
        result[key] = value
    return result


def load_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"),
                           object_pairs_hook=_unique_object_pairs)
    except FileNotFoundError:
        raise ValueError("Configuration file not found: {}".format(path))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON: {}".format(exc))
    except ValueError as exc:
        raise ValueError("Invalid JSON: {}".format(exc))
    except OSError as exc:
        raise ValueError("Unable to read JSON: {}".format(exc))
    if not isinstance(value, dict):
        raise ValueError("Configuration root must be a JSON object")
    return value


def write_json_file(path, value):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        ".{}.{}.tmp".format(path.name, uuid.uuid4().hex))
    temporary.write_text(
        json.dumps(
            value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8")
    os.replace(str(temporary), str(path))


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


def records_sha256(records):
    payload = "\n".join(sorted(
        json.dumps(record, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True)
        for record in records))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def artifact_content_hash(artifact):
    identity = {
        key: value for key, value in artifact.items()
        if key != "content_hash"
    }
    payload = json.dumps(
        identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def reviewed_set_sha256(records, artifact):
    work_items = [
        record for record in records if record.get("kind") == "work_item"
    ]
    selected = work_items + [artifact]
    selected.extend(
        record for record in records
        if record.get("kind") == "finding")
    selected.extend(
        record for record in records
        if record.get("kind") == "verification"
        and record.get("artifact_id") == artifact.get("id")
        and record.get("artifact_version") == artifact.get("version")
        and record.get("status") == "PASS"
        and not record.get("closure_gate")
        and record.get("role") in {"verifier", "reviewer", "challenger"})
    return records_sha256(selected)


def execution_errors(verification):
    execution = verification.get("execution")
    if not isinstance(execution, dict):
        return ["Verification {} execution metadata is missing".format(
            json.dumps(verification.get("id"), ensure_ascii=True))]
    errors = []
    required = {"command", "exit_code", "executed_at"}
    missing = sorted(required - set(execution))
    if missing:
        errors.append(
            "Verification {} execution missing fields: {}".format(
                json.dumps(verification.get("id"), ensure_ascii=True),
                _quoted_names(missing)))
    extra = sorted(set(execution) - required)
    if extra:
        errors.append(
            "Verification {} execution unknown fields: {}".format(
                json.dumps(verification.get("id"), ensure_ascii=True),
                _quoted_names(extra)))
    if (not isinstance(execution.get("command"), str)
            or not execution.get("command").strip()):
        errors.append("Verification execution command must be non-blank")
    exit_code = execution.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        errors.append("Verification execution exit_code must be an integer")
    elif verification.get("status") == "PASS" and exit_code != 0:
        errors.append("PASS Verification execution exit_code must be 0")
    elif verification.get("status") == "FAIL" and exit_code == 0:
        errors.append("FAIL Verification execution exit_code must be non-zero")
    try:
        datetime.datetime.fromisoformat(execution.get("executed_at", ""))
    except (TypeError, ValueError):
        errors.append("Verification execution executed_at is invalid")
    return errors


def decision_history_errors(decisions, allow_no_terminal):
    errors = []
    cycles = []
    for decision in decisions:
        cycle = decision.get("cycle")
        if (isinstance(cycle, bool) or not isinstance(cycle, int)
                or cycle < 1):
            errors.append("Decision cycle must be a positive integer")
        else:
            cycles.append(cycle)
    if len(cycles) != len(set(cycles)):
        errors.append("Decision cycles must be unique")
    terminal = [
        decision for decision in decisions
        if decision.get("decision") in {"ACCEPT", "STOP", "ESCALATE"}
    ]
    if not allow_no_terminal and not terminal:
        errors.append("records require a final terminal Decision")
    if len(terminal) > 1:
        errors.append("records must contain exactly one terminal Decision")
    if terminal and cycles:
        final_cycle = max(cycles)
        terminal_cycles = {
            decision.get("cycle") for decision in terminal
            if isinstance(decision.get("cycle"), int)
        }
        if final_cycle not in terminal_cycles:
            errors.append("terminal Decision must be the last cycle")
    return errors


def artifact_source_errors(artifact, repo_root):
    if artifact.get("artifact_type") != "working_tree_change":
        return []
    errors = []
    revision = artifact.get("source_revision")
    if not isinstance(revision, str) or not re.fullmatch(
            r"[0-9a-f]{40}", revision):
        errors.append("working_tree_change Artifact source_revision is invalid")
        return errors
    file_hashes = artifact.get("file_hashes")
    files = artifact.get("files")
    if (not isinstance(file_hashes, dict)
            or not isinstance(files, list)
            or set(file_hashes) != set(files)):
        errors.append(
            "working_tree_change Artifact file_hashes must match files")
        return errors
    if repo_root is None:
        errors.append(
            "working_tree_change Artifact requires --repo for file verification")
        return errors
    repo_root = Path(repo_root).resolve()
    for relative, expected in sorted(file_hashes.items()):
        try:
            process = subprocess.run(
                ["git", "show", "{}:{}".format(revision, relative)],
                cwd=str(repo_root), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False)
        except OSError as exc:
            errors.append("Unable to run git for source verification: {}".format(
                exc))
            break
        if process.returncode != 0:
            errors.append(
                "Unable to resolve source file {} at {}".format(
                    relative, revision))
            continue
        actual = hashlib.sha256(process.stdout).hexdigest()
        if actual != expected:
            errors.append("Artifact source file hash does not match: {}".format(
                relative))
    return errors


def legacy_roleless_ids(records, work_item_id):
    try:
        manifest = load_json(MIGRATION_MANIFEST)
    except ValueError:
        return set(), "migration manifest unavailable"
    if type(manifest.get("schema_version")) is not int or (
            manifest.get("schema_version") != 1):
        return set(), "migration manifest schema_version must be 1"
    if manifest.get("digest_algorithm") != (
            "SHA-256 over sorted compact JSON records joined by LF"):
        return set(), "migration manifest digest_algorithm is invalid"
    migrations = manifest.get("migrations")
    if not isinstance(migrations, list):
        return set(), "migration manifest migrations must be an array"
    seen = set()
    matched = None
    for migration in migrations:
        if not isinstance(migration, dict):
            return set(), "migration manifest entries must be objects"
        migration_work_item = migration.get("work_item_id")
        if (not isinstance(migration_work_item, str)
                or not STABLE_ID.fullmatch(migration_work_item)):
            return set(), "migration manifest work_item_id is invalid"
        from_version = migration.get("from_schema_version")
        to_version = migration.get("to_schema_version")
        if (type(from_version) is not int or from_version != 2
                or type(to_version) is not int or to_version != 3):
            return set(), "migration manifest versions must be 2 to 3"
        record_count = migration.get("record_count")
        if type(record_count) is not int or record_count < 0:
            return set(), "migration manifest record_count is invalid"
        if not isinstance(
                migration.get("pre_migration_snapshot_retained"), bool):
            return set(), "migration manifest snapshot flag is invalid"
        roles = migration.get("role_fields_present_before_rewrite")
        if (not isinstance(roles, dict)
                or not all(
                    isinstance(key, str) and STABLE_ID.fullmatch(key)
                    and value in {
                        "producer", "verifier", "reviewer", "challenger",
                        "arbiter"}
                    for key, value in roles.items())):
            return set(), "migration manifest pre-existing roles are invalid"
        disclosure = migration.get("disclosure")
        if not isinstance(disclosure, str) or not disclosure.strip():
            return set(), "migration manifest disclosure must be non-blank"
        ids = migration.get("roleless_verification_ids")
        if (not isinstance(ids, list)
                or not all(
                    isinstance(item, str) and STABLE_ID.fullmatch(item)
                    for item in ids)
                or len(ids) != len(set(ids))):
            return set(), "migration manifest roleless ids are invalid"
        digest = migration.get("records_sha256")
        if not isinstance(digest, str) or not re.fullmatch(
                r"[0-9a-f]{64}", digest):
            return set(), "migration manifest records_sha256 is invalid"
        key = (migration_work_item, from_version, to_version)
        if key in seen:
            return set(), "migration manifest duplicate migration entry"
        seen.add(key)
        if migration_work_item == work_item_id:
            matched = migration
    if matched is None:
        return set(), None
    if matched["record_count"] != len(records):
        return set(), "migration manifest record_count does not match"
    if matched["records_sha256"] != records_sha256(records):
        return set(), "legacy migration record digest mismatch"
    actual_roles = {
        record.get("id"): record.get("role")
        for record in records
        if record.get("kind") == "verification"
        and record.get("role") is not None
    }
    if matched["role_fields_present_before_rewrite"] != actual_roles:
        return set(), "migration manifest role disclosure does not match"
    actual_roleless = {
        record.get("id")
        for record in records
        if record.get("kind") == "verification"
        and record.get("role") is None
    }
    if set(matched["roleless_verification_ids"]) != actual_roleless:
        return set(), "migration manifest roleless IDs do not match"
    return set(matched["roleless_verification_ids"]), None


def schema_errors(value, schema, path="$"):
    errors = []
    expected_type = schema.get("type")
    valid_type = True
    if expected_type == "object":
        valid_type = isinstance(value, dict)
    elif expected_type == "array":
        valid_type = isinstance(value, list)
    elif expected_type == "string":
        valid_type = isinstance(value, str)
    elif expected_type == "boolean":
        valid_type = isinstance(value, bool)
    elif expected_type == "integer":
        valid_type = isinstance(value, int) and not isinstance(value, bool)
    if not valid_type:
        return ["{} must be {}".format(path, expected_type)]
    if "const" in schema and value != schema["const"]:
        errors.append("{} must equal {}".format(path, json.dumps(schema["const"])))
    if "enum" in schema and value not in schema["enum"]:
        errors.append("{} has invalid value".format(path))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append("{} is too short".format(path))
        pattern = schema.get("pattern")
        if pattern and not re.search(pattern, value):
            errors.append("{} has invalid format".format(path))
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("{} is below minimum".format(path))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append("{} has too few items".format(path))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append("{} has too many items".format(path))
        if schema.get("uniqueItems") and len(value) != len({
                json.dumps(item, sort_keys=True) for item in value}):
            errors.append("{} items must be unique".format(path))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(schema_errors(
                    item, item_schema, "{}[{}]".format(path, index)))
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = sorted(set(schema.get("required", [])) - set(value))
        if missing:
            errors.append("{} missing fields: {}".format(
                path, _quoted_names(missing)))
        if len(value) < schema.get("minProperties", 0):
            errors.append("{} has too few properties".format(path))
        property_names = schema.get("propertyNames")
        if isinstance(property_names, dict):
            for key in value:
                errors.extend(schema_errors(
                    key, property_names, "{}.<key>".format(path)))
        additional = schema.get("additionalProperties")
        for key, item in value.items():
            child_path = "{}.{}".format(path, key)
            if key in properties:
                errors.extend(schema_errors(item, properties[key], child_path))
            elif additional is False:
                errors.append("{} is not allowed".format(child_path))
            elif isinstance(additional, dict):
                errors.extend(schema_errors(item, additional, child_path))
    for child in schema.get("allOf", []):
        errors.extend(schema_errors(value, child, path))
    if isinstance(schema.get("if"), dict):
        condition_errors = schema_errors(value, schema["if"], path)
        if not condition_errors and isinstance(schema.get("then"), dict):
            errors.extend(schema_errors(value, schema["then"], path))
    if isinstance(schema.get("not"), dict):
        if not schema_errors(value, schema["not"], path):
            errors.append("{} must not satisfy forbidden schema".format(path))
    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and not any(
            not schema_errors(value, child, path) for child in any_of):
        errors.append("{} must satisfy anyOf".format(path))
    return errors


def finding_errors(value):
    required = {
        "schema_version", "id", "kind", "source_role", "severity", "target",
        "claim", "evidence", "impact", "required_action", "criterion_ids",
        "status",
    }
    optional = {"recurrence_of", "prevention"}
    errors = []
    missing = sorted(required - set(value))
    if missing:
        errors.append("missing fields: {}".format(_quoted_names(missing)))
    extra = sorted(set(value) - required - optional)
    if extra:
        errors.append("unknown fields: {}".format(_quoted_names(extra)))
    if value.get("schema_version") != 3:
        errors.append("schema_version must be 3")
    if value.get("kind") != "finding":
        errors.append("kind must be finding")
    finding_id = value.get("id")
    if not isinstance(finding_id, str) or not STABLE_ID.fullmatch(finding_id):
        errors.append("id must be a stable ID")
    source_role = value.get("source_role")
    if not isinstance(source_role, str) or source_role not in {
            "producer", "verifier", "reviewer", "challenger", "arbiter"}:
        errors.append("invalid source_role")
    for field in ("target", "claim", "impact", "required_action"):
        if not isinstance(value.get(field), str) or not value.get(field).strip():
            errors.append("{} must be a non-empty string".format(field))
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not evidence or not all(
            isinstance(item, str) and item.strip() for item in evidence):
        errors.append("evidence must be a non-empty string array")
    criterion_ids = value.get("criterion_ids")
    if not isinstance(criterion_ids, list) or not criterion_ids or not all(
            isinstance(item, str) and STABLE_ID.fullmatch(item)
            for item in criterion_ids):
        errors.append("criterion_ids must be a non-empty stable ID array")
    elif len(criterion_ids) != len(set(criterion_ids)):
        errors.append("criterion_ids must be unique")

    severity = value.get("severity")
    status = value.get("status")
    severity_valid = (
        isinstance(severity, str)
        and severity in {"low", "medium", "high", "blocking"}
    )
    status_valid = (
        isinstance(status, str)
        and status in {"open", "resolved", "accepted_risk", "not_reproducible"}
    )
    if not severity_valid:
        errors.append("invalid severity")
    if not status_valid:
        errors.append("invalid status")
    severity_blocks = severity_valid and severity in {"high", "blocking"}
    if severity_blocks and status == "accepted_risk":
        errors.append("high or blocking finding cannot be accepted_risk")

    has_recurrence = "recurrence_of" in value
    needs_prevention = (
        has_recurrence
        or (
            status_valid
            and status in {"resolved", "not_reproducible"}
            and severity_blocks
        )
    )
    prevention = value.get("prevention")
    if "prevention" in value and not isinstance(prevention, dict):
        errors.append("prevention must be an object")
    if needs_prevention and not isinstance(prevention, dict):
        errors.append("resolved high/blocking finding or recurrence requires prevention")
    if isinstance(prevention, dict):
        p_required = {
            "kind", "action", "evidence", "regression_verification_ids"
        }
        p_missing = sorted(p_required - set(prevention))
        if p_missing:
            errors.append(
                "prevention missing fields: {}".format(_quoted_names(p_missing)))
        p_extra = sorted(set(prevention) - p_required - {"fallback_reason"})
        if p_extra:
            errors.append(
                "prevention unknown fields: {}".format(_quoted_names(p_extra)))
        kind = prevention.get("kind")
        if not isinstance(kind, str) or kind not in {
                "structure", "automatic_check", "skill_rule", "human_review"}:
            errors.append("invalid prevention kind")
            kind = None
        for field in ("action",):
            if (not isinstance(prevention.get(field), str)
                    or not prevention.get(field).strip()):
                errors.append("prevention {} must be a non-empty string".format(field))
        for field in ("evidence",):
            items = prevention.get(field)
            if not isinstance(items, list) or not items or not all(
                    isinstance(item, str) and item.strip() for item in items):
                errors.append("prevention {} must be a non-empty string array".format(field))
        if "regression_verification_ids" in prevention:
            ids = prevention.get("regression_verification_ids")
            if not isinstance(ids, list) or not ids or not all(
                    isinstance(item, str) and STABLE_ID.fullmatch(item)
                    for item in ids):
                errors.append(
                    "regression_verification_ids must be a non-empty string array of stable IDs")
            elif len(ids) != len(set(ids)):
                errors.append("regression_verification_ids must be unique")
        reason = prevention.get("fallback_reason")
        if "fallback_reason" in prevention and (
                not isinstance(reason, str) or not reason.strip()):
            errors.append("fallback_reason must be a non-empty string")
        if kind in {"automatic_check", "skill_rule", "human_review"}:
            if not isinstance(reason, str) or not reason.strip():
                errors.append(
                    "non-structure prevention requires fallback_reason")
    recurrence = value.get("recurrence_of")
    if "recurrence_of" in value and (
            not isinstance(recurrence, str) or not STABLE_ID.fullmatch(recurrence)):
        errors.append("recurrence_of must be a stable ID")
    elif recurrence == value.get("id"):
        errors.append("recurrence_of must not be self-referential")
    return errors


def verification_errors(
        finding, work_item, artifact, verifications, pre_closure=False):
    errors = []
    prevention = finding.get("prevention")
    if not isinstance(prevention, dict):
        return errors
    refs = prevention.get("regression_verification_ids")
    if not isinstance(refs, list) or not refs:
        return errors
    work_required = {
        "schema_version", "id", "kind", "goal", "pack_id", "constraints",
        "priority", "risk_level", "control_tier", "route_flags",
        "max_repair_iterations",
        "acceptance_criteria",
    }
    work_missing = sorted(work_required - set(work_item))
    if work_missing:
        errors.append(
            "Work Item missing fields: {}".format(_quoted_names(work_missing)))
    work_extra = sorted(set(work_item) - work_required - {"open_questions"})
    if work_extra:
        errors.append(
            "Work Item unknown fields: {}".format(_quoted_names(work_extra)))
    if work_item.get("schema_version") != 3 or work_item.get("kind") != "work_item":
        errors.append("Work Item schema_version/kind is invalid")
    if not isinstance(work_item.get("id"), str) or not STABLE_ID.fullmatch(
            work_item.get("id", "")):
        errors.append("Work Item id must be a stable ID")
    for field in ("goal", "pack_id"):
        if (not isinstance(work_item.get(field), str)
                or not work_item.get(field).strip()):
            errors.append("Work Item {} must be non-blank".format(field))
    constraints = work_item.get("constraints")
    if not isinstance(constraints, list) or not all(
            isinstance(item, str) and item.strip() for item in constraints):
        errors.append("Work Item constraints must be a non-blank string array")
    priority = work_item.get("priority")
    if not isinstance(priority, str) or priority not in {
            "low", "medium", "high", "critical"}:
        errors.append("Work Item priority is invalid")
    risk_level = work_item.get("risk_level")
    if not isinstance(risk_level, str) or risk_level not in {
            "low", "medium", "high", "critical"}:
        errors.append("Work Item risk_level is invalid")
    if work_item.get("control_tier") not in {"L0", "L1", "L2", "L3"}:
        errors.append("Work Item control_tier must be L0-L3")
    route_flags = work_item.get("route_flags")
    if (not isinstance(route_flags, dict)
            or set(route_flags) != {"trivial", "ambiguous", "irreversible"}
            or not all(isinstance(value, bool)
                       for value in route_flags.values())):
        errors.append("Work Item route_flags must contain three booleans")
    if (isinstance(work_item.get("max_repair_iterations"), bool)
            or not isinstance(work_item.get("max_repair_iterations"), int)
            or work_item.get("max_repair_iterations") < 0):
        errors.append(
            "Work Item max_repair_iterations must be a non-negative integer")
    if "open_questions" in work_item:
        questions = work_item.get("open_questions")
        if not isinstance(questions, list) or not all(
                isinstance(item, str) and item.strip() for item in questions):
            errors.append(
                "Work Item open_questions must be a non-blank string array")
    criteria = work_item.get("acceptance_criteria")
    if not isinstance(criteria, dict) or not criteria:
        return ["work item acceptance_criteria must be a non-empty object"]
    if not all(
            isinstance(key, str) and STABLE_ID.fullmatch(key)
            and isinstance(value, str) and value.strip()
            for key, value in criteria.items()):
        errors.append(
            "Work Item acceptance_criteria must map stable IDs to non-blank text")
    artifact_required = {
        "schema_version", "id", "kind", "artifact_type", "version",
        "content", "source", "work_item_id", "files", "content_hash",
    }
    artifact_missing = sorted(artifact_required - set(artifact))
    if artifact_missing:
        errors.append(
            "Artifact missing fields: {}".format(_quoted_names(artifact_missing)))
    artifact_extra = sorted(
        set(artifact) - artifact_required - {
            "producer_context", "source_revision", "file_hashes",
            "evidence_path"})
    if artifact_extra:
        errors.append(
            "Artifact unknown fields: {}".format(_quoted_names(artifact_extra)))
    if artifact.get("schema_version") != 3 or artifact.get("kind") != "artifact":
        errors.append("Artifact schema_version/kind is invalid")
    if not isinstance(artifact.get("id"), str) or not STABLE_ID.fullmatch(
            artifact.get("id", "")):
        errors.append("Artifact id must be a stable ID")
    if not isinstance(artifact.get("work_item_id"), str) or not STABLE_ID.fullmatch(
            artifact.get("work_item_id", "")):
        errors.append("Artifact work_item_id must be a stable ID")
    files = artifact.get("files")
    if not isinstance(files, list) or not files or not all(
            isinstance(item, str) and item.strip() for item in files):
        errors.append("Artifact files must be a non-empty non-blank string array")
    elif len(files) != len(set(files)):
        errors.append("Artifact files must be unique")
    for field in ("artifact_type", "version", "content", "source"):
        if (not isinstance(artifact.get(field), str)
                or not artifact.get(field).strip()):
            errors.append(
                "Artifact {} must be non-blank".format(field))
    if artifact.get("work_item_id") != work_item.get("id"):
        errors.append("artifact work_item_id does not match Work Item")
    stored_hash = artifact.get("content_hash")
    if (not isinstance(stored_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", stored_hash)):
        errors.append("Artifact content_hash must be a SHA-256 hex digest")
    elif stored_hash != artifact_content_hash(artifact):
        errors.append("Artifact content_hash does not match canonical identity")
    by_id = {}
    for verification in verifications:
        verification_id = verification.get("id")
        if not isinstance(verification_id, str) or not STABLE_ID.fullmatch(verification_id):
            errors.append("Verification id must be a stable ID")
            continue
        if verification_id in by_id:
            errors.append("duplicate Verification id: {}".format(verification_id))
            continue
        by_id[verification_id] = verification
    covered_criteria = set()
    for verification_id in refs:
        verification = by_id.get(verification_id)
        if verification is None:
            errors.append(
                "regression Verification {} not found".format(verification_id))
            continue
        required = {
            "schema_version", "id", "kind", "artifact_id", "artifact_version",
            "artifact_content_hash", "criterion_ids", "check", "method",
            "status", "evidence", "limitations", "finding_id",
        }
        missing = sorted(required - set(verification))
        if missing:
            errors.append(
                "Verification {} missing fields: {}".format(
                    verification_id, _quoted_names(missing)))
        extra = sorted(
            set(verification) - required - {
                "role", "host_context", "execution", "closure_gate"})
        if extra:
            errors.append(
                "Verification {} unknown fields: {}".format(
                    verification_id, _quoted_names(extra)))
        if verification.get("schema_version") != 3:
            errors.append(
                "Verification {} schema_version must be 3".format(
                    verification_id))
        if verification.get("kind") != "verification":
            errors.append(
                "Verification {} kind must be verification".format(
                    verification_id))
        if ("role" in verification
                and verification.get("role") not in {
                    "producer", "verifier", "reviewer", "challenger",
                    "arbiter"}):
            errors.append(
                "Verification {} role is invalid".format(verification_id))
        if verification.get("finding_id") != finding.get("id"):
            errors.append(
                "Verification {} finding_id mismatch".format(verification_id))
        for field in ("check", "method"):
            if (not isinstance(verification.get(field), str)
                    or not verification.get(field).strip()):
                errors.append(
                    "Verification {} {} must be non-blank".format(
                        verification_id, field))
        status_passes = (
            verification.get("status") == "PASS"
            or (pre_closure
                and verification.get("closure_gate") is True
                and finding.get("closure_gate") is True))
        if not status_passes:
            errors.append(
                "regression Verification {} is not PASS".format(verification_id))
        evidence = verification.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(
                isinstance(item, str) and item.strip() for item in evidence):
            errors.append(
                "regression Verification {} has no executed evidence".format(
                    verification_id))
        if verification.get("artifact_id") != artifact.get("id"):
            errors.append(
                "regression Verification {} artifact id mismatch".format(
                    verification_id))
        if verification.get("artifact_version") != artifact.get("version"):
            errors.append(
                "regression Verification {} artifact version mismatch".format(
                    verification_id))
        if (verification.get("artifact_content_hash")
                != artifact.get("content_hash")):
            errors.append(
                "regression Verification {} artifact content hash mismatch".format(
                    verification_id))
        if not (
                pre_closure
                and verification.get("closure_gate") is True
                and verification.get("status") != "PASS"):
            errors.extend(execution_errors(verification))
        verification_criteria = verification.get("criterion_ids")
        if not isinstance(verification_criteria, list) or not verification_criteria:
            errors.append(
                "regression Verification {} has no criterion_ids".format(
                    verification_id))
        elif not all(
                isinstance(item, str) and STABLE_ID.fullmatch(item)
                for item in verification_criteria):
            errors.append(
                "regression Verification {} has invalid criterion_ids".format(
                    verification_id))
        elif len(verification_criteria) != len(set(verification_criteria)):
            errors.append(
                "regression Verification {} criterion_ids must be unique".format(
                    verification_id))
        elif not set(verification_criteria).issubset(set(criteria)):
            errors.append(
                "regression Verification {} references unknown criterion".format(
                    verification_id))
        else:
            covered_criteria.update(verification_criteria)
        limitations = verification.get("limitations")
        if (not isinstance(limitations, list)
                or not all(
                    isinstance(item, str) and item.strip()
                    for item in limitations)):
            errors.append(
                "Verification {} limitations must be a non-blank string array".format(
                    verification_id))
    finding_criteria = finding.get("criterion_ids")
    if isinstance(finding_criteria, list) and finding_criteria:
        missing_criteria = set(finding_criteria) - covered_criteria
        if missing_criteria:
            errors.append(
                "regression evidence does not cover Finding criterion_ids: {}".format(
                    _quoted_names(sorted(missing_criteria))))
    return errors


def check_finding(path, work_item_path=None, artifact_path=None,
                  verifications_dir=None):
    try:
        value = load_json(path)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    errors = finding_errors(value)
    prevention = value.get("prevention")
    refs = prevention.get("regression_verification_ids") if isinstance(
        prevention, dict) else None
    refs_valid = (
        isinstance(refs, list)
        and bool(refs)
        and all(
            isinstance(item, str) and STABLE_ID.fullmatch(item)
            for item in refs)
    )
    if refs_valid:
        context = (work_item_path, artifact_path, verifications_dir)
        if not all(context):
            errors.append(
                "regression verification evidence requires --work-item, "
                "--artifact, and --verifications-dir")
        else:
            try:
                work_item = load_json(work_item_path)
                artifact = load_json(artifact_path)
                directory = Path(verifications_dir)
                if not directory.is_dir():
                    raise ValueError(
                        "Verification directory not found: {}".format(directory))
                verifications = []
                for item in sorted(directory.glob("*.json")):
                    record = load_json(item)
                    if record.get("kind") == "verification":
                        verifications.append(record)
            except ValueError as exc:
                print("ERROR: {}".format(exc), file=sys.stderr)
                return 2
            errors.extend(verification_errors(
                value, work_item, artifact, verifications))
    if errors:
        display_id = json.dumps(value.get("id", "finding"), ensure_ascii=True)
        print("[FAIL] {}".format(display_id), file=sys.stderr)
        for error in errors:
            print("ERROR: {}".format(error), file=sys.stderr)
        return 1
    print("[PASS] {}".format(value["id"]))
    return 0


def iteration_lineage(iterations, artifact_versions, max_repair_iterations,
                      work_item_id):
    errors = []
    cycles = []
    declared_outputs = set()
    for iteration in iterations:
        if iteration.get("work_item_id") != work_item_id:
            errors.append("Iteration work_item_id does not match Work Item")
        cycle = iteration.get("cycle")
        if isinstance(cycle, int) and not isinstance(cycle, bool) and cycle > 0:
            cycles.append(cycle)
        else:
            errors.append("Iteration cycle must be a positive integer")
        inputs = iteration.get("input_versions")
        if (not isinstance(inputs, list) or not inputs or not all(
                isinstance(item, str) and item.strip() for item in inputs)):
            errors.append("Iteration input_versions must be a non-empty array")
        elif len(inputs) != len(set(inputs)):
            errors.append("Iteration input_versions must be unique")
        produced = iteration.get("output_versions")
        if not isinstance(produced, list) or not all(
                isinstance(item, str) and item.strip() for item in produced):
            errors.append("Iteration output_versions must be an array")
        elif len(produced) != len(set(produced)):
            errors.append("Iteration output_versions must be unique")
        else:
            declared_outputs.update(produced)
    if cycles:
        if sorted(cycles) != list(range(1, len(cycles) + 1)):
            errors.append("Iteration cycles must be contiguous from 1")
    initial = artifact_versions - declared_outputs
    if len(initial) != 1:
        errors.append("Artifact lineage must start with exactly one version")
        return set(), errors
    current = set(initial)
    repairs = 0
    ordered = sorted(
        iterations,
        key=lambda item: item.get("cycle", 0)
        if isinstance(item.get("cycle"), int) else 0)
    for iteration in ordered:
        inputs = iteration.get("input_versions")
        if isinstance(inputs, list) and set(inputs) != current:
            errors.append("Iteration inputs must match the current lineage")
        produced = iteration.get("output_versions")
        if not isinstance(produced, list) or not produced:
            continue
        repairs += 1
        if len(produced) != 1:
            errors.append("Artifact repair Iteration must produce one version")
        valid_outputs = {
            version for version in produced
            if isinstance(version, str) and version in artifact_versions}
        unknown = set(produced) - valid_outputs
        if unknown:
            errors.append("Iteration output versions not found: {}".format(
                _quoted_names(sorted(unknown))))
        if valid_outputs & current:
            errors.append("Iteration output version already exists in lineage")
        if valid_outputs:
            current = valid_outputs
    if repairs > max_repair_iterations:
        errors.append("Artifact repairs exceed max_repair_iterations")
    return current, errors


def _host_context_errors(context, label, require_independence=False):
    if not isinstance(context, dict):
        return ["{} must be an object".format(label)]
    required = {"session_id", "model", "authentication"}
    if require_independence:
        required.add("independence")
    errors = []
    missing = sorted(required - set(context))
    if missing:
        errors.append("{} missing fields: {}".format(
            label, _quoted_names(missing)))
    extra = sorted(set(context) - required)
    if extra:
        errors.append("{} unknown fields: {}".format(
            label, _quoted_names(extra)))
    for field in ("session_id", "model"):
        if (not isinstance(context.get(field), str)
                or not context.get(field).strip()):
            errors.append("{} {} must be non-blank".format(label, field))
    if context.get("authentication") != "unverified_host_attestation":
        errors.append(
            "{} must use unverified_host_attestation".format(label))
    if (require_independence
            and context.get("independence") != "independent"):
        errors.append(
            "{} requires independent host attestation".format(label))
    return errors


def l3_host_provenance_errors(work_item, artifact, verifications):
    if work_item.get("control_tier") != "L3" or artifact is None:
        return []
    errors = []
    producer_context = artifact.get("producer_context")
    producer_errors = _host_context_errors(
        producer_context, "Artifact producer_context")
    errors.extend(producer_errors)
    producer_session = (
        producer_context.get("session_id")
        if isinstance(producer_context, dict) else None)
    producer_model = (
        producer_context.get("model")
        if isinstance(producer_context, dict) else None)
    passing = {}
    for role in ("reviewer", "challenger"):
        passes = [
            record for record in verifications
            if record.get("kind") == "verification"
            and record.get("role") == role
            and record.get("status") == "PASS"
            and record.get("artifact_id") == artifact.get("id")
            and record.get("artifact_version") == artifact.get("version")
        ]
        valid_sessions = set()
        valid_models = set()
        for verification in passes:
            label = "{} host_context".format(role.capitalize())
            context = verification.get("host_context")
            context_errors = _host_context_errors(
                context, label, require_independence=True)
            errors.extend(context_errors)
            session_id = (
                context.get("session_id") if isinstance(context, dict)
                else None)
            model = (
                context.get("model") if isinstance(context, dict)
                else None)
            if (not context_errors and producer_session is not None
                    and session_id == producer_session):
                errors.append(
                    "{} must use a different host session than "
                    "producer_context".format(label))
            elif (not context_errors and producer_model is not None
                  and model == producer_model):
                errors.append(
                    "{} must use a different model than "
                    "producer_context".format(label))
            elif not context_errors:
                valid_sessions.add(session_id)
                valid_models.add(model)
        if passes:
            passing[role] = (valid_sessions, valid_models)
            if not valid_sessions:
                errors.append(
                    "{} requires a valid independent host attestation".format(
                        role.capitalize()))
    if passing.get("reviewer") and passing.get("challenger"):
        reviewer_sessions, reviewer_models = passing["reviewer"]
        challenger_sessions, challenger_models = passing["challenger"]
        if reviewer_sessions & challenger_sessions:
            errors.append(
                "Reviewer and Challenger require distinct host sessions")
        if reviewer_models & challenger_models:
            errors.append(
                "Reviewer and Challenger require distinct models")
    return errors


def records_errors(records, repo_root=None, pre_closure=False):
    errors = []
    groups = {}
    schema_valid = True
    for record in records:
        kind = record.get("kind")
        if not isinstance(kind, str):
            errors.append("record kind must be a string")
            schema_valid = False
            continue
        if kind not in SCHEMA_FILES:
            errors.append("unknown record kind {}".format(
                json.dumps(kind, ensure_ascii=True)))
            schema_valid = False
            continue
        if kind in {
                "work_item", "artifact", "finding", "verification",
                "decision", "iteration", "approval"}:
            groups.setdefault(kind, []).append(record)
            try:
                schema = load_json(SCHEMA_ROOT / SCHEMA_FILES[kind])
            except ValueError as exc:
                errors.append("{} schema unavailable: {}".format(kind, exc))
                schema_valid = False
            else:
                record_schema_errors = schema_errors(record, schema)
                if record_schema_errors:
                    schema_valid = False
                    errors.extend("{} schema: {}".format(kind, error)
                                  for error in record_schema_errors)
    if not schema_valid:
        return errors

    global_ids = {}
    for kind, kind_records in groups.items():
        if kind == "artifact":
            continue
        for record in kind_records:
            record_id = record.get("id")
            if record_id in global_ids:
                errors.append(
                    "cross-record ID conflict {}: {} and {}".format(
                        record_id, global_ids[record_id], kind))
            else:
                global_ids[record_id] = kind

    work_items = groups.get("work_item", [])
    if len(work_items) != 1:
        errors.append("records must contain exactly one Work Item")
        return errors
    work_item = work_items[0]
    work_item_id = work_item.get("id")
    control_tier = work_item.get("control_tier")
    if control_tier not in {"L0", "L1", "L2", "L3"}:
        errors.append("Work Item control_tier must be L0-L3")
    route_flags = work_item.get("route_flags")
    if (not isinstance(route_flags, dict)
            or set(route_flags) != {"trivial", "ambiguous", "irreversible"}
            or not all(isinstance(value, bool)
                       for value in route_flags.values())):
        errors.append(
            "Work Item route_flags must contain three booleans")
        route_flags = {}
    legacy_roleless, migration_error = legacy_roleless_ids(
        records, work_item_id)
    if migration_error:
        errors.append(migration_error)
    criteria = work_item.get("acceptance_criteria")
    if not isinstance(work_item_id, str) or not STABLE_ID.fullmatch(work_item_id):
        errors.append("Work Item id must be a stable ID")
    if not isinstance(criteria, dict) or not criteria:
        errors.append("Work Item acceptance_criteria must be a non-empty object")
        criteria = {}

    for kind in (
            "finding", "verification", "decision", "iteration", "approval"):
        seen = set()
        for record in groups.get(kind, []):
            record_id = record.get("id")
            if not isinstance(record_id, str) or not STABLE_ID.fullmatch(record_id):
                errors.append("{} id must be a stable ID".format(kind))
                continue
            if record_id in seen:
                errors.append("duplicate {} id: {}".format(kind, record_id))
            seen.add(record_id)

    artifacts = groups.get("artifact", [])
    if not artifacts:
        errors.append("records must contain at least one Artifact")
    artifact_keys = set()
    artifact_ids = set()
    artifact_versions = set()
    artifacts_by_key = {}
    for artifact in artifacts:
        artifact_id = artifact.get("id")
        version = artifact.get("version")
        if artifact.get("work_item_id") != work_item_id:
            errors.append("Artifact work_item_id does not match Work Item")
        if not isinstance(artifact_id, str) or not STABLE_ID.fullmatch(artifact_id):
            errors.append("Artifact id must be a stable ID")
            continue
        if not isinstance(version, str) or not version.strip():
            errors.append("Artifact version must be non-blank")
            continue
        key = (artifact_id, version)
        if key in artifact_keys:
            errors.append("duplicate Artifact id/version: {}/{}".format(
                artifact_id, version))
        artifact_keys.add(key)
        artifacts_by_key[key] = artifact
        artifact_ids.add(artifact_id)
        artifact_versions.add(version)
        if artifact.get("content_hash") != artifact_content_hash(artifact):
            errors.append(
                "Artifact content_hash does not match canonical identity")
    if len(artifact_ids) != 1:
        errors.append("Stage 2 record checks require one Artifact lineage")
    tier_rank = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
    if control_tier in tier_rank and artifacts:
        planned = route_plan(
            work_item.get("risk_level", "low"),
            max(len(item.get("files", [])) for item in artifacts),
            bool(route_flags.get("trivial")),
            bool(route_flags.get("ambiguous")),
            bool(route_flags.get("irreversible")))
        if tier_rank[control_tier] < tier_rank.get(planned["tier"], 3):
            errors.append("control_tier is lower than the selected route")

    findings = {}
    finding_criteria = set(criteria)
    for finding in groups.get("finding", []):
        finding_id = finding.get("id")
        if isinstance(finding_id, str):
            findings[finding_id] = finding
        ids = finding.get("criterion_ids")
        if (not isinstance(ids, list)
                or not all(isinstance(item, str) for item in ids)):
            errors.append("Finding criterion_ids must be a string array")
        else:
            unknown = set(ids) - finding_criteria
            if unknown:
                errors.append("Finding references unknown criteria: {}".format(
                    _quoted_names(sorted(unknown))))

    for finding_id in findings:
        current = finding_id
        seen = set()
        while current in findings:
            if current in seen:
                errors.append("Finding recurrence cycle detected at {}".format(
                    finding_id))
                break
            seen.add(current)
            recurrence = findings[current].get("recurrence_of")
            if recurrence is None:
                break
            if not isinstance(recurrence, str):
                errors.append("Finding recurrence_of must be a stable ID")
                break
            if recurrence not in findings:
                errors.append("Finding recurrence target not found: {}".format(
                    recurrence))
                break
            current = recurrence

    final_versions, lineage_errors = iteration_lineage(
        groups.get("iteration", []),
        artifact_versions,
        work_item.get("max_repair_iterations", 0),
        work_item_id)
    errors.extend(lineage_errors)

    verifications = {}
    for verification in groups.get("verification", []):
        verification_id = verification.get("id")
        if isinstance(verification_id, str):
            verifications[verification_id] = verification
        artifact_id = verification.get("artifact_id")
        artifact_version = verification.get("artifact_version")
        if (not isinstance(artifact_id, str)
                or not isinstance(artifact_version, str)):
            errors.append("Verification artifact id/version must be strings")
        elif (artifact_id, artifact_version) not in artifact_keys:
            errors.append("Verification {} artifact version {} not found".format(
                verification_id,
                json.dumps(artifact_version, ensure_ascii=True)))
        elif (verification.get("artifact_content_hash")
              != artifacts_by_key[
                  (artifact_id, artifact_version)].get("content_hash")):
            errors.append(
                "Verification {} artifact content hash does not match".format(
                    verification_id))
        ids = verification.get("criterion_ids")
        if (not isinstance(ids, list)
                or not all(isinstance(item, str) for item in ids)):
            errors.append("Verification criterion_ids must be a string array")
        else:
            unknown = set(ids) - finding_criteria
            if unknown:
                errors.append("Verification references unknown criteria: {}".format(
                    _quoted_names(sorted(unknown))))
        finding_id = verification.get("finding_id")
        if finding_id is not None and finding_id not in findings:
            errors.append("Verification {} references unknown Finding".format(
                verification_id))
        if verification.get("status") not in {
                "PASS", "FAIL", "BLOCKED", "NOT_RUN"}:
            errors.append("Verification {} has invalid status".format(
                verification_id))
        evidence = verification.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(
                isinstance(item, str) and item.strip() for item in evidence):
            errors.append("Verification {} has no executed evidence".format(
                verification_id))
    for verification_id in legacy_roleless:
        verification = verifications.get(verification_id)
        if verification is None:
            errors.append(
                "legacy roleless Verification {} does not resolve".format(
                    verification_id))
        elif verification.get("role") is not None:
            errors.append(
                "legacy roleless Verification {} declares a role".format(
                    verification_id))
    approvals = {}
    for approval in groups.get("approval", []):
        approval_id = approval.get("id")
        approvals[approval_id] = approval
        if approval.get("work_item_id") != work_item_id:
            errors.append("Approval work_item_id does not match Work Item")
        artifact_id = approval.get("artifact_id")
        artifact_version = approval.get("artifact_version")
        if (artifact_id, artifact_version) not in artifact_keys:
            errors.append("Approval {} Artifact version not found".format(
                approval_id))
        elif (approval.get("artifact_content_hash")
              != artifacts_by_key[
                  (artifact_id, artifact_version)].get("content_hash")):
            errors.append(
                "Approval {} artifact content hash does not match".format(
                    approval_id))
        expected = "APPROVE {}@{}".format(artifact_id, artifact_version)
        if approval.get("confirmation") != expected:
            errors.append("Approval {} confirmation is invalid".format(
                approval_id))
        approver = approval.get("approver")
        if (not isinstance(approver, str)
                or approver.strip().lower() == "controller"):
            errors.append("Approval {} requires a human approver".format(
                approval_id))
        try:
            datetime.datetime.fromisoformat(approval.get("approved_at", ""))
        except (TypeError, ValueError):
            errors.append("Approval {} approved_at is invalid".format(
                approval_id))

    final_artifact = None
    if len(final_versions) == 1:
        final_version = next(iter(final_versions))
        final_artifact = next(
            (artifact for artifact in artifacts
             if artifact.get("version") == final_version),
            None)
    errors.extend(l3_host_provenance_errors(
        work_item, final_artifact, list(verifications.values())))
    if final_artifact is not None:
        errors.extend(artifact_source_errors(
            final_artifact, repo_root or Path.cwd()))
    for finding_id, finding in findings.items():
        if final_artifact is not None:
            errors.extend(verification_errors(
                finding, work_item, final_artifact,
                list(verifications.values()), pre_closure))

    decisions = groups.get("decision", [])
    if not decisions:
        errors.append("records must contain at least one Decision")
    errors.extend(decision_history_errors(decisions, allow_no_terminal=False))
    decision_cycles = [
        decision.get("cycle") for decision in decisions
        if isinstance(decision.get("cycle"), int)]
    if len(decisions) > 1:
        if (len(decision_cycles) != len(decisions)
                or any(
                    earlier >= later
                    for earlier, later in zip(
                        sorted(decision_cycles),
                        sorted(decision_cycles)[1:]))):
            errors.append(
                "multiple Decisions require unique, strictly increasing cycles")
    terminal_decisions = [
        decision for decision in decisions
        if decision.get("decision") in {"ACCEPT", "STOP", "ESCALATE"}]
    if len(terminal_decisions) != 1:
        errors.append(
            "records must contain exactly one final ACCEPT/STOP/ESCALATE Decision")
    final_decision = terminal_decisions[0] if len(
        terminal_decisions) == 1 else None
    if (final_decision is not None and decision_cycles
            and isinstance(final_decision.get("cycle"), int)
            and final_decision.get("cycle") != max(decision_cycles)):
        errors.append("final ACCEPT Decision must be the last cycle")
    if decision_cycles:
        ordered_decisions = sorted(
            decisions,
            key=lambda item: item.get("cycle", 0)
            if isinstance(item.get("cycle"), int) else 0)
        for index, decision in enumerate(ordered_decisions[:-1]):
            if decision.get("decision") in {"STOP", "ESCALATE"}:
                errors.append(
                    "terminal Decision cannot have a later Decision")
                break
    iterations_by_cycle = {
        iteration.get("cycle"): iteration
        for iteration in groups.get("iteration", [])
        if isinstance(iteration.get("cycle"), int)}
    repair_decisions = {
        decision.get("cycle"): decision
        for decision in decisions
        if (decision.get("decision") == "REPAIR"
            and isinstance(decision.get("cycle"), int))}
    decisions_by_cycle = {
        decision.get("cycle"): decision
        for decision in decisions
        if isinstance(decision.get("cycle"), int)}
    for iteration in groups.get("iteration", []):
        decision = decisions_by_cycle.get(iteration.get("cycle"))
        if decision is None and iteration.get("result") != "CONTINUE":
            errors.append(
                "non-CONTINUE Iteration requires a same-cycle Decision")
        elif (decision is not None
              and iteration.get("result") != decision.get("decision")):
            errors.append(
                "Iteration result must match same-cycle Decision")
    for decision in decisions:
        cycle = decision.get("cycle")
        if (isinstance(cycle, bool) or not isinstance(cycle, int)
                or cycle < 1):
            errors.append("Decision cycle must be a positive integer")
        if decision.get("work_item_id") != work_item_id:
            errors.append("Decision work_item_id does not match Work Item")
        versions = decision.get("artifact_versions")
        if not isinstance(versions, list) or not versions:
            errors.append("Decision artifact_versions must be non-empty")
            versions = []
        for version in versions:
            if not isinstance(version, str):
                errors.append("Decision artifact versions must be strings")
            elif version not in artifact_versions:
                errors.append("Decision artifact version {} not found".format(
                    json.dumps(version, ensure_ascii=True)))
        hashes = decision.get("artifact_hashes")
        if not isinstance(hashes, dict):
            errors.append("Decision artifact_hashes must be an object")
        else:
            if set(hashes) != set(versions):
                errors.append(
                    "Decision artifact_hashes must exactly match artifact_versions")
            for version in versions:
                artifact = next(
                    (item for item in artifacts
                     if item.get("version") == version), None)
                if (artifact is not None
                        and hashes.get(version) != artifact.get("content_hash")):
                    errors.append(
                        "Decision artifact hash does not match version {}".format(
                            json.dumps(version, ensure_ascii=True)))
        refs = decision.get("evidence_refs")
        if isinstance(refs, list):
            for ref in refs:
                if (ref not in findings and ref not in verifications
                        and ref not in approvals):
                    errors.append(
                        "Decision evidence_ref {} does not resolve".format(
                            json.dumps(ref, ensure_ascii=True)))
                elif (ref in verifications
                      and verifications[ref].get("artifact_version")
                      not in versions):
                    errors.append(
                        "Decision evidence_ref {} targets a future Artifact version".format(
                            json.dumps(ref, ensure_ascii=True)))
                elif (ref in approvals
                      and approvals[ref].get("artifact_version")
                      not in versions):
                    errors.append(
                        "Decision approval_ref {} targets a future Artifact version".format(
                            json.dumps(ref, ensure_ascii=True)))
        if decision is final_decision and decision.get("decision") == "ACCEPT":
            if work_item.get("open_questions"):
                errors.append("open_questions block ACCEPT")
            risk_level = work_item.get("risk_level")
            independence = decision.get("review_independence")
            if (control_tier in {"L2", "L3"}
                    and independence != "independent"):
                errors.append(
                    "ACCEPT requires independent review for this control tier")
            approver = decision.get("approver")
            ref_verifications = [
                verifications[ref] for ref in decision.get("evidence_refs", [])
                if ref in verifications]
            ref_approvals = [
                approvals[ref] for ref in decision.get("evidence_refs", [])
                if ref in approvals]
            expected_reviewed_set = (
                reviewed_set_sha256(records, final_artifact)
                if final_artifact is not None else None)
            if decision.get("reviewed_set_digest") != expected_reviewed_set:
                errors.append(
                    "ACCEPT reviewed_set_digest does not match reviewed records")
            for approval in ref_approvals:
                if approval.get("reviewed_set_digest") != expected_reviewed_set:
                    errors.append(
                        "Approval reviewed_set_digest does not match reviewed records")
            for verification in ref_verifications:
                if not (
                        pre_closure
                        and verification.get("closure_gate") is True
                        and verification.get("status") != "PASS"):
                    errors.extend(execution_errors(verification))
            reviewer_evidence = (
                final_artifact is not None
                and any(
                    verification.get("role") == "reviewer"
                    and verification.get("status") == "PASS"
                    and verification.get("artifact_id")
                    == final_artifact.get("id")
                    and verification.get("artifact_version")
                    == final_artifact.get("version")
                    for verification in ref_verifications))
            if control_tier in {"L2", "L3"} and not reviewer_evidence:
                errors.append(
                    "ACCEPT requires a final-version PASS Reviewer Verification")
            challenger_evidence = (
                final_artifact is not None
                and any(
                    verification.get("role") == "challenger"
                    and verification.get("status") == "PASS"
                    and verification.get("artifact_id")
                    == final_artifact.get("id")
                    and verification.get("artifact_version")
                    == final_artifact.get("version")
                    for verification in ref_verifications))
            if control_tier == "L3" and not challenger_evidence:
                errors.append(
                    "L3 ACCEPT requires final-version PASS Challenger evidence")
            if (control_tier == "L3"
                    and (not isinstance(approver, str)
                         or approver.strip().lower() == "controller")):
                errors.append("L3 ACCEPT requires human approval")
            if control_tier == "L3":
                human_approval = (
                    final_artifact is not None
                    and any(
                        item.get("artifact_id") == final_artifact.get("id")
                        and item.get("artifact_version")
                        == final_artifact.get("version")
                        and item.get("approver") == approver
                        for item in ref_approvals))
                if not human_approval:
                    errors.append(
                        "L3 ACCEPT requires referenced human approval record")
            if decision.get("unresolved_disagreements"):
                errors.append("unresolved disagreements block ACCEPT")
            if any(
                    finding.get("status") == "open"
                    and finding.get("severity") in {"high", "blocking"}
                    for finding in findings.values()):
                errors.append("open high/blocking finding blocks ACCEPT")
            evidence_map = decision.get("criteria_evidence")
            if not isinstance(evidence_map, dict):
                errors.append("ACCEPT requires criteria_evidence")
                evidence_map = {}
            if len(final_versions) != 1:
                errors.append("Decision requires one final Artifact version")
                final_version = None
            else:
                final_version = next(iter(final_versions))
                if set(versions) != {final_version}:
                    errors.append(
                        "Decision must accept the final Artifact version")
            medium_risks = [
                finding_id for finding_id, finding in findings.items()
                if finding.get("severity") == "medium"
                and finding.get("status") in {"open", "accepted_risk"}]
            risk_finding_ids = {
                risk.get("finding_id")
                for risk in decision.get("residual_risks", [])
                if isinstance(risk, dict)}
            missing_risks = set(medium_risks) - risk_finding_ids
            if missing_risks:
                errors.append(
                    "accepted medium Findings require residual_risks: {}".format(
                        _quoted_names(sorted(missing_risks))))
            for risk in decision.get("residual_risks", []):
                finding_id = risk.get("finding_id") if isinstance(
                    risk, dict) else None
                if finding_id is not None and finding_id not in findings:
                    errors.append(
                        "residual risk references unknown Finding {}".format(
                            json.dumps(finding_id, ensure_ascii=True)))
            if set(evidence_map) != set(criteria):
                errors.append("Decision criteria_evidence must match Work Item criteria")
            for criterion_id, evidence in evidence_map.items():
                verification_ids = evidence.get("verification_ids") if isinstance(
                    evidence, dict) else None
                if (not isinstance(verification_ids, list)
                        or not verification_ids
                        or not all(
                            isinstance(item, str)
                            for item in verification_ids)):
                    errors.append(
                        "Decision criterion {} has no verification_ids".format(
                            criterion_id))
                    continue
                has_verifier_evidence = False
                for verification_id in verification_ids:
                    verification = verifications.get(verification_id)
                    if verification is None:
                        errors.append(
                            "Decision verification {} not found".format(
                                json.dumps(verification_id, ensure_ascii=True)))
                        continue
                    verifier_passes = (
                        not verification.get("closure_gate")
                        and verification.get("status") == "PASS")
                    if not verifier_passes:
                        errors.append(
                            "Decision verification {} is not PASS".format(
                                json.dumps(verification_id, ensure_ascii=True)))
                    if verification.get("artifact_version") not in versions:
                        errors.append(
                            "Decision verification {} has stale artifact version".format(
                                json.dumps(verification_id, ensure_ascii=True)))
                    if (final_version is not None
                            and verification.get("artifact_version") != final_version):
                        errors.append(
                            "Decision verification {} does not target the final Artifact version".format(
                                json.dumps(verification_id, ensure_ascii=True)))
                    if criterion_id not in verification.get("criterion_ids", []):
                        errors.append(
                            "Decision verification {} does not cover {}".format(
                                json.dumps(verification_id, ensure_ascii=True),
                                json.dumps(criterion_id, ensure_ascii=True)))
                    if not (
                            pre_closure
                            and verification.get("closure_gate") is True
                            and verification.get("status") != "PASS"):
                        errors.extend(execution_errors(verification))
                    has_verifier_role = (
                        verification.get("role") == "verifier"
                        or (
                            verification.get("role") is None
                            and verification_id in legacy_roleless))
                    if (has_verifier_role
                            and verifier_passes
                            and final_artifact is not None
                            and verification.get("artifact_id")
                            == final_artifact.get("id")
                            and verification.get("artifact_version")
                            == final_version
                            and criterion_id
                            in verification.get("criterion_ids", [])):
                        has_verifier_evidence = True
                if not has_verifier_evidence:
                    errors.append(
                        "Decision criterion {} requires a final-version Verifier Verification role".format(
                            criterion_id))
        elif decision.get("decision") == "REPAIR":
            for field in ("next_state", "repair_kind"):
                if not isinstance(decision.get(field), str):
                    errors.append("REPAIR requires {}".format(field))
            iteration = iterations_by_cycle.get(decision.get("cycle"))
            if iteration is None:
                errors.append("REPAIR requires an Iteration in the same cycle")
            repair_kind = decision.get("repair_kind")
            next_state = decision.get("next_state")
            produced = iteration.get("output_versions") if iteration else []
            if repair_kind == "artifact":
                if next_state != "PRODUCE":
                    errors.append(
                        "artifact REPAIR requires next_state PRODUCE")
                if not produced:
                    errors.append(
                        "artifact REPAIR requires a new Artifact version")
                if iteration is not None:
                    inputs = iteration.get("input_versions")
                    if not isinstance(inputs, list) or sorted(inputs) != sorted(
                            versions):
                        errors.append(
                            "artifact REPAIR versions must match Iteration input_versions")
            elif repair_kind == "evidence":
                if next_state != "VERIFY":
                    errors.append(
                        "evidence REPAIR requires next_state VERIFY")
                if produced:
                    errors.append(
                        "evidence REPAIR must not produce an Artifact version")
                if iteration is not None:
                    inputs = iteration.get("input_versions")
                    if not isinstance(inputs, list) or sorted(inputs) != sorted(
                            versions):
                        errors.append(
                            "evidence REPAIR versions must match Iteration input_versions")

    for iteration in groups.get("iteration", []):
        produced = iteration.get("output_versions")
        if not isinstance(produced, list) or not produced:
            continue
        repair = repair_decisions.get(iteration.get("cycle"))
        if repair is None or repair.get("repair_kind") != "artifact":
            errors.append(
                "Artifact-producing Iteration requires an artifact REPAIR")
    if (final_decision is not None
            and isinstance(final_decision.get("cycle"), int)):
        final_cycle = final_decision["cycle"]
        if any(
                isinstance(iteration.get("cycle"), int)
                and iteration["cycle"] > final_cycle
                for iteration in groups.get("iteration", [])):
            errors.append(
                "Iteration cannot follow the final terminal Decision")
    for decision in terminal_decisions:
        if "next_state" in decision or "repair_kind" in decision:
            errors.append(
                "terminal Decision must not contain repair fields")

    return errors


def check_records(directory, repo=None, pre_closure=False):
    root = Path(directory)
    if not root.is_dir():
        print("ERROR: Records directory not found: {}".format(root),
              file=sys.stderr)
        return 2
    records = []
    try:
        for path in sorted(root.rglob("*.json")):
            record = load_json(path)
            records.append(record)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    errors = records_errors(records, repo, pre_closure)
    if errors:
        blocked = any(error.startswith("BLOCKED:") for error in errors)
        print("[BLOCKED] records" if blocked else "[FAIL] records",
              file=sys.stderr)
        for error in errors:
            print("ERROR: {}".format(json.dumps(error, ensure_ascii=True)),
                  file=sys.stderr)
        return 3 if blocked else 1
    work_item = next(x for x in records if x.get("kind") == "work_item")
    print("[PASS] {} records={} artifacts={} cycles={}".format(
        work_item["id"],
        len(records),
        sum(x.get("kind") == "artifact" for x in records),
        sum(x.get("kind") == "iteration" for x in records)))
    return 0


def migration_journal_path(root):
    root = Path(root).resolve()
    return root.parent / ".{}.migration-transaction.json".format(root.name)


def recover_migration_transaction(root):
    root = Path(root).resolve()
    journal = migration_journal_path(root)
    if not journal.exists():
        return None, None
    try:
        data = load_json(journal)
    except ValueError as exc:
        return None, str(exc)
    if type(data.get("schema_version")) is not int or (
            data.get("schema_version") != 1):
        return None, "migration journal schema_version is invalid"
    if data.get("phase") not in {"prepared", "backed_up", "committed"}:
        return None, "migration journal phase is invalid"
    journal_paths = {
        field: data.get(field) for field in ("root", "backup", "stage")
    }
    if not all(
            isinstance(value, str) and value.strip()
            for value in journal_paths.values()):
        return None, "migration journal paths are invalid"
    if not Path(journal_paths["root"]).is_absolute():
        return None, "migration journal root must be absolute"
    if Path(journal_paths["root"]).resolve() != root:
        return None, "migration journal root does not match"
    backup = Path(journal_paths["backup"])
    stage = Path(journal_paths["stage"])
    backup_prefix = root.name + ".migration-backup-"
    stage_prefix = root.name + ".migration-stage-"
    if (not backup.is_absolute() or not stage.is_absolute()
            or backup.parent.resolve() != root.parent
            or stage.parent.resolve() != root.parent
            or not backup.name.startswith(backup_prefix)
            or not stage.name.startswith(stage_prefix)
            or backup == stage or backup.is_symlink() or stage.is_symlink()):
        return None, "migration journal paths are invalid"
    try:
        if root.exists():
            if stage.exists():
                shutil.rmtree(stage)
            journal.unlink()
            return "kept_current", None
        if backup.exists():
            os.replace(str(backup), str(root))
            if stage.exists():
                shutil.rmtree(stage)
            journal.unlink()
            return "rolled_back", None
        if stage.exists():
            os.replace(str(stage), str(root))
            journal.unlink()
            return "rolled_forward", None
    except OSError as exc:
        return None, str(exc)
    return None, "migration journal has no recoverable directory"


def acquire_migration_lock(root):
    root = Path(root).resolve()
    path = root.parent / ".{}.migration.lock".format(root.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None, path
    return fd, path


def release_migration_lock(fd, path):
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def migrate_records(directory, write=False, verification_roles=None,
                    record_criteria=None, execution_evidence=None):
    fd, lock_path = acquire_migration_lock(directory)
    if fd is None:
        print("ERROR: migration already active for {}".format(directory),
              file=sys.stderr)
        return 2
    try:
        return _migrate_records(
            directory, write, verification_roles, record_criteria,
            execution_evidence)
    finally:
        release_migration_lock(fd, lock_path)


def _migrate_records(directory, write=False, verification_roles=None,
                     record_criteria=None, execution_evidence=None):
    root = Path(directory)
    recovered, recovery_error = recover_migration_transaction(root)
    if recovery_error:
        print("ERROR: migration recovery failed: {}".format(recovery_error),
              file=sys.stderr)
        return 2
    if not root.is_dir():
        print("ERROR: Records directory not found: {}".format(root),
              file=sys.stderr)
        return 2
    roles = {}
    for spec in verification_roles or []:
        if "=" not in spec:
            print("ERROR: --verification-role must be ID=ROLE", file=sys.stderr)
            return 2
        record_id, role = spec.split("=", 1)
        if (not STABLE_ID.fullmatch(record_id)
                or role not in {
                    "producer", "verifier", "reviewer", "challenger",
                    "arbiter"}):
            print("ERROR: invalid --verification-role {}".format(spec),
                  file=sys.stderr)
            return 2
        if record_id in roles:
            print("ERROR: duplicate --verification-role {}".format(record_id),
                  file=sys.stderr)
            return 2
        roles[record_id] = role
    execution_map = {}
    if execution_evidence:
        try:
            execution_map = load_json(execution_evidence)
        except ValueError as exc:
            print("ERROR: {}".format(exc), file=sys.stderr)
            return 2
        for record_id, value in execution_map.items():
            errors = execution_errors({
                "id": record_id,
                "status": "PASS",
                "execution": value,
            })
            if errors:
                print(
                    "ERROR: execution evidence {} is invalid: {}".format(
                        json.dumps(record_id, ensure_ascii=True),
                        "; ".join(errors)),
                    file=sys.stderr)
                return 2
    criteria_overrides = {}
    for spec in record_criteria or []:
        if "=" not in spec:
            print("ERROR: --record-criteria must be ID=AC-1,AC-2",
                  file=sys.stderr)
            return 2
        record_id, criteria_text = spec.split("=", 1)
        criteria_ids = [
            item for item in criteria_text.split(",") if item
        ]
        if (not STABLE_ID.fullmatch(record_id)
                or not criteria_ids
                or not all(STABLE_ID.fullmatch(item)
                           for item in criteria_ids)
                or len(criteria_ids) != len(set(criteria_ids))):
            print("ERROR: invalid --record-criteria {}".format(spec),
                  file=sys.stderr)
            return 2
        if record_id in criteria_overrides:
            print("ERROR: duplicate --record-criteria {}".format(record_id),
                  file=sys.stderr)
            return 2
        criteria_overrides[record_id] = criteria_ids
    paths = sorted(root.rglob("*.json"))
    if not paths:
        print("ERROR: Records directory contains no JSON files",
              file=sys.stderr)
        return 2
    records = []
    try:
        for path in paths:
            records.append((path, load_json(path)))
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    versions = {}
    for path, record in records:
        version = record.get("schema_version")
        if type(version) is not int or version not in {1, 2, 3}:
            print("ERROR: {} has unsupported schema_version".format(path),
                  file=sys.stderr)
            return 2
        versions[path] = version
    migrated = {
        path: record for path, record in records
        if record.get("schema_version") in {1, 2}
    }
    for path, record in records:
        if record.get("schema_version") != 3:
            continue
        kind = record.get("kind")
        if ((kind == "artifact"
             and "content_hash" not in record)
                or (kind == "verification"
                    and ("artifact_content_hash" not in record
                         or "role" not in record
                         or "execution" not in record))
                or (kind in {"decision", "approval"}
                    and "reviewed_set_digest" not in record)
                or (kind == "decision"
                    and "artifact_hashes" not in record)
                or (kind == "approval"
                    and "artifact_content_hash" not in record)):
            migrated[path] = record
    verification_ids = {
        record.get("id") for _, record in records
        if record.get("kind") == "verification"
    }
    unknown_execution = sorted(set(execution_map) - verification_ids)
    if unknown_execution:
        print(
            "ERROR: --execution-evidence references unknown Verification {}"
            .format(_quoted_names(unknown_execution)),
            file=sys.stderr)
        return 2
    work_items = [
        record for _, record in records
        if record.get("kind") == "work_item"
    ]
    if len(work_items) != 1:
        print("ERROR: migration requires exactly one Work Item",
              file=sys.stderr)
        return 1
    work_item = work_items[0]
    legacy_roleless, legacy_error = legacy_roleless_ids(
        [record for _, record in records], work_item.get("id"))
    if legacy_error:
        print("ERROR: {}".format(legacy_error), file=sys.stderr)
        return 1
    criteria_map = {}
    if versions[next(
            path for path, record in records if record is work_item)] == 1:
        criteria_values = work_item.get("acceptance_criteria")
        if (not isinstance(criteria_values, list)
                or not criteria_values
                or not all(
                    isinstance(item, str) and item.strip()
                    for item in criteria_values)
                or len(criteria_values) != len(set(criteria_values))):
            print(
                "ERROR: v1 acceptance_criteria must be unique non-blank strings",
                file=sys.stderr)
            return 1
        criteria_map = {
            criterion: "AC-{}".format(index)
            for index, criterion in enumerate(criteria_values, 1)
        }
        work_item["acceptance_criteria"] = {
            criterion_id: criterion
            for criterion, criterion_id in criteria_map.items()
        }
    artifacts = [
        record for _, record in records if record.get("kind") == "artifact"
    ]
    file_count = max(
        (len(record.get("files", [])) for record in artifacts), default=1)
    flags = work_item.get("route_flags", {})
    planned_route = route_plan(
        work_item.get("risk_level", "low"),
        file_count,
        bool(flags.get("trivial", False)),
        bool(flags.get("ambiguous", False)),
        bool(flags.get("irreversible", False)))

    decisions = sorted(
        ((path, record) for path, record in records
         if record.get("kind") == "decision"),
        key=lambda item: str(item[0]))
    criteria_for_verification = {}
    for path, record in decisions:
        evidence = record.get("criteria_evidence")
        if isinstance(evidence, list):
            converted = {}
            for item in evidence:
                criterion = item.get("criterion") if isinstance(
                    item, dict) else None
                criterion_id = criteria_map.get(criterion)
                if criterion_id is None or criterion_id in converted:
                    print(
                        "ERROR: v1 Decision criterion cannot be mapped: {}".format(
                            json.dumps(criterion, ensure_ascii=True)),
                        file=sys.stderr)
                    return 1
                verification_ids = item.get("verification_ids")
                if (not isinstance(verification_ids, list)
                        or not verification_ids
                        or not all(
                            isinstance(value, str)
                            and STABLE_ID.fullmatch(value)
                            for value in verification_ids)
                        or len(verification_ids) != len(
                            set(verification_ids))):
                    print(
                        "ERROR: v1 criteria_evidence verification_ids are invalid",
                        file=sys.stderr)
                    return 1
                converted[criterion_id] = {
                    "verification_ids": verification_ids,
                    "result": item.get("result"),
                }
                for verification_id in verification_ids:
                    criteria_for_verification.setdefault(
                        verification_id, set()).add(criterion_id)
            record["criteria_evidence"] = converted
    used_cycles = {
        record.get("cycle") for _, record in decisions
        if type(record.get("cycle")) is int and record.get("cycle") > 0
    }
    next_cycle = 1
    decision_cycles = {}
    for path, record in decisions:
        if record.get("cycle") is None:
            while next_cycle in used_cycles:
                next_cycle += 1
            decision_cycles[path] = next_cycle
            used_cycles.add(next_cycle)
            next_cycle += 1

    transforms = []
    for path in sorted(migrated):
        record = migrated[path]
        kind = record.get("kind")
        if kind == "work_item":
            record.setdefault("control_tier", planned_route["tier"])
            record.setdefault("route_flags", {
                "trivial": False,
                "ambiguous": False,
                "irreversible": False,
            })
            record.setdefault("max_repair_iterations", 3)
        elif kind == "artifact":
            record.setdefault("files", [record.get("source")])
        elif kind == "verification":
            record_id = record.get("id")
            if record.get("role") is None:
                if record_id in roles:
                    record["role"] = roles[record_id]
                elif record_id in legacy_roleless:
                    record["role"] = "verifier"
                else:
                    print(
                        "ERROR: Verification {} requires --verification-role".format(
                            record_id),
                        file=sys.stderr)
                    return 1
            if "criterion_ids" not in record:
                if record_id in criteria_overrides:
                    record["criterion_ids"] = (
                        criteria_overrides[record_id])
                elif record_id in criteria_for_verification:
                    record["criterion_ids"] = sorted(
                        criteria_for_verification[record_id])
                else:
                    print(
                        "ERROR: Verification {} requires --record-criteria".format(
                            record_id),
                        file=sys.stderr)
                    return 1
            record.setdefault("limitations", [])
            if "execution" not in record:
                if record_id in execution_map:
                    record["execution"] = execution_map[record_id]
                elif record.get("status") == "PASS":
                    print(
                        "ERROR: Verification {} requires --execution-evidence"
                        .format(record_id),
                        file=sys.stderr)
                    return 1
        elif kind == "finding":
            if "criterion_ids" not in record:
                record_id = record.get("id")
                if record_id not in criteria_overrides:
                    print(
                        "ERROR: Finding {} requires --record-criteria".format(
                            record_id),
                        file=sys.stderr)
                    return 1
                record["criterion_ids"] = criteria_overrides[record_id]
        elif kind == "decision":
            if record.get("cycle") is None:
                record["cycle"] = decision_cycles[path]
            if record.get("decision") == "ACCEPT":
                record.setdefault("residual_risks", [])
                record.setdefault("review_independence", "non_independent")
        record["schema_version"] = 3
        transforms.append({
            "file": str(path.relative_to(root)),
            "kind": kind,
        })

    artifact_lookup = {
        (record.get("id"), record.get("version")): record
        for _, record in records if record.get("kind") == "artifact"
    }
    artifact_ids = {
        key[0] for key in artifact_lookup
    }
    for record in artifact_lookup.values():
        record["content_hash"] = artifact_content_hash(record)
    for path in sorted(migrated):
        record = migrated[path]
        if record.get("kind") == "verification":
            key = (record.get("artifact_id"), record.get("artifact_version"))
            artifact = artifact_lookup.get(key)
            if artifact is None:
                print(
                    "ERROR: Verification {} references an unknown Artifact".format(
                        record.get("id")),
                    file=sys.stderr)
                return 1
            record["artifact_content_hash"] = artifact.get("content_hash")
        elif record.get("kind") == "decision":
            versions = record.get("artifact_versions")
            if isinstance(versions, list) and len(artifact_ids) == 1:
                artifact_id = next(iter(artifact_ids))
                record["artifact_hashes"] = {
                    version: artifact_lookup[
                        (artifact_id, version)].get("content_hash")
                    for version in versions
                    if (artifact_id, version) in artifact_lookup
                }
        elif record.get("kind") == "approval":
            key = (record.get("artifact_id"), record.get("artifact_version"))
            artifact = artifact_lookup.get(key)
            if artifact is None:
                print(
                    "ERROR: Approval {} references an unknown Artifact".format(
                        record.get("id")),
                    file=sys.stderr)
                return 1
            record["artifact_content_hash"] = artifact.get("content_hash")

    if len(artifact_ids) == 1:
        review_artifact_id = next(iter(artifact_ids))
        review_records = [record for _, record in records]
        for path in sorted(migrated):
            record = migrated[path]
            if record.get("kind") not in {"decision", "approval"}:
                continue
            artifact = artifact_lookup.get((
                review_artifact_id, record.get("artifact_version")))
            if artifact is None:
                versions = record.get("artifact_versions", [])
                if len(versions) == 1:
                    artifact = artifact_lookup.get((
                        review_artifact_id, versions[0]))
            if artifact is not None:
                record["reviewed_set_digest"] = reviewed_set_sha256(
                    review_records, artifact)

    finding_ids = {
        record.get("id") for _, record in records
        if record.get("kind") == "finding"
    }
    verification_ids = {
        record.get("id") for _, record in records
        if record.get("kind") == "verification"
    }
    stable_ids = finding_ids | verification_ids
    for path, record in decisions:
        if path not in migrated:
            continue
        refs = record.get("evidence_refs")
        if not isinstance(refs, list):
            continue
        notes = record.setdefault("evidence_notes", [])
        stable_refs = [
            ref for ref in refs
            if isinstance(ref, str) and ref in stable_ids
        ]
        unresolved = [
            ref for ref in refs
            if isinstance(ref, str) and ref not in stable_ids
        ]
        notes.extend(
            "Migrated evidence: {}".format(ref) for ref in unresolved)
        if not stable_refs:
            versions = set(record.get("artifact_versions", []))
            if record.get("decision") == "ACCEPT":
                stable_refs = sorted(
                    record.get("id")
                    for _, record in records
                    if record.get("kind") == "verification"
                    and record.get("status") == "PASS"
                    and record.get("artifact_version") in versions
                )
            elif record.get("decision") == "REPAIR":
                stable_refs = sorted(finding_ids)
        if not stable_refs:
            print(
                "ERROR: {} has no resolvable evidence_refs".format(path),
                file=sys.stderr)
            return 1
        record["evidence_refs"] = sorted(set(stable_refs))

    transformed_records = [record for _, record in records]
    errors = records_errors(transformed_records)
    if errors:
        print("[FAIL] migration validation", file=sys.stderr)
        for error in errors:
            print("ERROR: {}".format(json.dumps(error, ensure_ascii=True)),
                  file=sys.stderr)
        return 1
    backup = None
    if write and migrated:
        stamp = datetime.datetime.now().astimezone().strftime(
            "%Y%m%d-%H%M%S-%f")
        stage = root.parent / "{}.migration-stage-{}".format(
            root.name, uuid.uuid4().hex)
        backup = root.parent / "{}.migration-backup-{}".format(
            root.name, stamp)
        journal = migration_journal_path(root)
        try:
            shutil.copytree(root, stage)
            for path in sorted(migrated):
                shadow = stage / path.relative_to(root)
                write_json_file(shadow, migrated[path])
            staged_records = [
                load_json(path) for path in sorted(stage.rglob("*.json"))
            ]
            errors = records_errors(staged_records)
            if errors:
                raise ValueError(
                    "staged migration validation failed: {}".format(
                        _quoted_names(errors)))
            write_json_file(journal, {
                "schema_version": 1,
                "root": str(root.resolve()),
                "backup": str(backup.resolve()),
                "stage": str(stage.resolve()),
                "phase": "prepared",
            })
            os.replace(str(root), str(backup))
            write_json_file(journal, {
                "schema_version": 1,
                "root": str(root.resolve()),
                "backup": str(backup.resolve()),
                "stage": str(stage.resolve()),
                "phase": "backed_up",
            })
            os.replace(str(stage), str(root))
            write_json_file(journal, {
                "schema_version": 1,
                "root": str(root.resolve()),
                "backup": str(backup.resolve()),
                "stage": str(stage.resolve()),
                "phase": "committed",
            })
            journal.unlink()
        except BaseException as exc:
            _, recovery_error = recover_migration_transaction(root)
            if stage.exists() and root.exists():
                shutil.rmtree(stage)
            print("ERROR: migration commit failed: {}".format(exc),
                  file=sys.stderr)
            if recovery_error:
                print("ERROR: migration recovery failed: {}".format(
                    recovery_error), file=sys.stderr)
            return 1
    print(json.dumps({
        "mode": "write" if write else "dry-run",
        "directory": str(root.resolve()),
        "changed": len(migrated),
        "backup": str(backup) if backup else None,
        "recovery": recovered,
        "transforms": transforms,
    }, indent=2, ensure_ascii=False))
    return 0


def load_runtime_records(directory):
    root = Path(directory).resolve()
    if not root.is_dir():
        raise ValueError("Records directory not found: {}".format(root))
    records = []
    for path in sorted(root.rglob("*.json")):
        records.append(load_json(path))
    if not records:
        raise ValueError("Records directory contains no JSON files")
    return root, records


def version_key(value):
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in re.split(r"(\d+)", str(value)) if part != "")


def final_artifact_record(records):
    work_items = [
        record for record in records if record.get("kind") == "work_item"
    ]
    artifacts = [
        record for record in records if record.get("kind") == "artifact"
    ]
    if not artifacts:
        return None
    if len(work_items) == 1:
        work_item = work_items[0]
        final_versions, errors = iteration_lineage(
            [record for record in records
             if record.get("kind") == "iteration"],
            {record.get("version") for record in artifacts},
            work_item.get("max_repair_iterations", 0),
            work_item.get("id"))
        if not errors and len(final_versions) == 1:
            version = next(iter(final_versions))
            return next(
                (record for record in artifacts
                 if record.get("version") == version),
                None)
    return sorted(
        artifacts, key=lambda record: version_key(record.get("version")))[-1]


def lineage_final_artifact(records):
    work_items = [
        record for record in records if record.get("kind") == "work_item"
    ]
    artifacts = [
        record for record in records if record.get("kind") == "artifact"
    ]
    if len(work_items) != 1 or not artifacts:
        return None, ["final Artifact lineage is unavailable"]
    work_item = work_items[0]
    final_versions, errors = iteration_lineage(
        [record for record in records if record.get("kind") == "iteration"],
        {record.get("version") for record in artifacts},
        work_item.get("max_repair_iterations", 0),
        work_item.get("id"))
    if errors:
        return None, errors
    if len(final_versions) != 1:
        return None, ["final Artifact lineage is ambiguous"]
    version = next(iter(final_versions))
    artifact = next(
        (record for record in artifacts
         if record.get("version") == version), None)
    if artifact is None:
        return None, ["final Artifact lineage does not resolve"]
    return artifact, []


def role_pass_exists(records, artifact, role):
    return bool(artifact) and any(
        record.get("kind") == "verification"
        and record.get("role") == role
        and record.get("status") == "PASS"
        and record.get("artifact_id") == artifact.get("id")
        and record.get("artifact_version") == artifact.get("version")
        for record in records)


def approval_exists(records, artifact, approver=None):
    return bool(artifact) and any(
        record.get("kind") == "approval"
        and record.get("artifact_id") == artifact.get("id")
        and record.get("artifact_version") == artifact.get("version")
        and (approver is None or record.get("approver") == approver)
        for record in records)


def runtime_record_errors(records, accept_gate=True):
    errors = []
    work_items = []
    for record in records:
        kind = record.get("kind")
        if not isinstance(kind, str) or kind not in SCHEMA_FILES:
            errors.append("record kind is invalid")
            continue
        try:
            schema = load_json(SCHEMA_ROOT / SCHEMA_FILES[kind])
        except ValueError as exc:
            errors.append("{} schema unavailable: {}".format(kind, exc))
            continue
        errors.extend(
            "{} schema: {}".format(kind, error)
            for error in schema_errors(record, schema))
        if kind == "work_item":
            work_items.append(record)
    if errors:
        return errors
    if len(work_items) != 1:
        errors.append("runtime requires exactly one Work Item")
        return errors
    work_item = work_items[0]
    work_item_id = work_item.get("id")
    criteria = set(work_item.get("acceptance_criteria", {}))
    decisions = [
        record for record in records if record.get("kind") == "decision"
    ]
    for error in decision_history_errors(
            decisions, allow_no_terminal=True):
        if error not in errors:
            errors.append(error)
    artifacts = [
        record for record in records if record.get("kind") == "artifact"
    ]
    artifact_ids = {record.get("id") for record in artifacts}
    artifact_versions = {record.get("version") for record in artifacts}
    artifacts_by_key = {
        (record.get("id"), record.get("version")): record
        for record in artifacts
    }
    for artifact in artifacts:
        if artifact.get("content_hash") != artifact_content_hash(artifact):
            errors.append(
                "Artifact content_hash does not match canonical identity")
    for record in records:
        kind = record.get("kind")
        if kind == "artifact" and record.get("work_item_id") != work_item_id:
            errors.append("Artifact work_item_id does not match Work Item")
        if kind == "decision" and record.get("work_item_id") != work_item_id:
            errors.append("Decision work_item_id does not match Work Item")
        if kind == "decision":
            versions = record.get("artifact_versions")
            if isinstance(versions, list):
                for version in versions:
                    if version not in artifact_versions:
                        errors.append(
                            "Decision artifact version does not resolve")
            hashes = record.get("artifact_hashes")
            if isinstance(versions, list) and isinstance(hashes, dict):
                if set(hashes) != set(versions):
                    errors.append(
                        "Decision artifact_hashes do not resolve")
                for version in versions:
                    artifact = next(
                        (item for item in artifacts
                         if item.get("version") == version), None)
                    if (artifact is not None
                            and hashes.get(version)
                            != artifact.get("content_hash")):
                        errors.append(
                            "Decision artifact hash does not resolve")
        if kind == "iteration" and record.get("work_item_id") != work_item_id:
            errors.append("Iteration work_item_id does not match Work Item")
        if (kind == "verification"
                and record.get("artifact_id") not in artifact_ids):
            errors.append("Verification artifact_id does not resolve")
        if kind == "verification":
            artifact = artifacts_by_key.get((
                record.get("artifact_id"), record.get("artifact_version")))
            if (artifact is not None
                    and record.get("artifact_content_hash")
                    != artifact.get("content_hash")):
                errors.append(
                    "Verification artifact content hash does not resolve")
            ids = record.get("criterion_ids")
            if isinstance(ids, list):
                unknown = set(ids) - criteria
                if unknown:
                    errors.append(
                        "Verification criterion_ids do not resolve")
        if kind == "finding":
            ids = record.get("criterion_ids")
            if isinstance(ids, list):
                unknown = set(ids) - criteria
                if unknown:
                    errors.append("Finding criterion_ids do not resolve")
        if kind == "approval":
            if record.get("work_item_id") != work_item_id:
                errors.append("Approval work_item_id does not match Work Item")
            key = (record.get("artifact_id"), record.get("artifact_version"))
            if key not in {
                    (artifact.get("id"), artifact.get("version"))
                    for artifact in artifacts}:
                errors.append("Approval artifact version does not resolve")
            elif (record.get("artifact_content_hash")
                  != artifacts_by_key[key].get("content_hash")):
                errors.append(
                    "Approval artifact content hash does not resolve")
    seen = {}
    for record in records:
        if record.get("kind") == "artifact":
            continue
        record_id = record.get("id")
        if record_id in seen:
            errors.append("cross-record ID conflict {}".format(record_id))
        else:
            seen[record_id] = record.get("kind")
    if artifacts:
        final_artifact, lineage_errors = lineage_final_artifact(records)
        for error in lineage_errors:
            if error not in errors:
                errors.append(error)
        for error in l3_host_provenance_errors(
                work_item, final_artifact, records):
            if error not in errors:
                errors.append(error)
    allowed_without_terminal = {
        "records must contain at least one Decision",
        "records require a final terminal Decision",
        "records must contain exactly one final ACCEPT/STOP/ESCALATE Decision",
    }
    for error in records_errors(
            records, Path.cwd(), pre_closure=True):
        if error in allowed_without_terminal:
            continue
        if error not in errors:
            errors.append(error)
    return errors


def derive_runtime_state(records, digest):
    work_item = next(
        record for record in records if record.get("kind") == "work_item")
    artifacts = [
        record for record in records if record.get("kind") == "artifact"
    ]
    verifications = [
        record for record in records if record.get("kind") == "verification"
    ]
    findings = [
        record for record in records if record.get("kind") == "finding"
    ]
    decisions = sorted(
        (record for record in records if record.get("kind") == "decision"),
        key=lambda record: record.get("cycle", 0))
    terminal = [
        record for record in decisions
        if record.get("decision") in {"ACCEPT", "STOP", "ESCALATE"}
    ]
    open_findings = sorted(
        record.get("id") for record in findings
        if record.get("status") == "open")
    blocking = [
        record for record in findings
        if record.get("status") == "open"
        and record.get("severity") in {"high", "blocking"}
    ]
    latest_artifact = final_artifact_record(records)
    final_verifications = [
        record for record in verifications
        if latest_artifact is not None
        and record.get("artifact_id") == latest_artifact.get("id")
        and record.get("artifact_version") == latest_artifact.get("version")
    ]
    delivery_verifications = [
        record for record in final_verifications
        if not record.get("closure_gate")
    ]
    criteria = set(work_item.get("acceptance_criteria", {}))
    verifier_coverage = {
        criterion_id
        for record in delivery_verifications
        if (record.get("role") == "verifier"
            and record.get("status") == "PASS")
        for criterion_id in record.get("criterion_ids", [])
    }
    final_failed = any(
        record.get("status") == "FAIL" for record in delivery_verifications)
    final_pending = (
        not delivery_verifications
        or any(
            record.get("status") in {"BLOCKED", "NOT_RUN"}
            for record in delivery_verifications)
        or not any(
            record.get("role") == "verifier"
            and record.get("status") == "PASS"
            for record in delivery_verifications)
        or not criteria.issubset(verifier_coverage))
    tier = work_item.get("control_tier")
    reviewer_pass = role_pass_exists(
        records, latest_artifact, "reviewer")
    challenger_pass = role_pass_exists(
        records, latest_artifact, "challenger")
    human_approval = approval_exists(records, latest_artifact)
    latest_terminal = terminal[-1] if terminal else None
    last_repair = (
        decisions[-1]
        if decisions and decisions[-1].get("decision") == "REPAIR"
        else None)
    repair_pending = False
    if last_repair is not None:
        repair_pending = last_repair.get("repair_kind") != "artifact"
        if last_repair.get("repair_kind") == "artifact":
            repair_pending = not any(
                record.get("kind") == "iteration"
                and record.get("cycle") == last_repair.get("cycle")
                and record.get("output_versions")
                for record in records)
    if (latest_terminal is not None
            and latest_terminal.get("decision") in {"STOP", "ESCALATE"}):
        decision = latest_terminal
        state = decision.get("decision")
        next_action = "none"
    elif repair_pending:
        decision = last_repair
        state = last_repair.get("next_state", "REPAIR")
        next_action = {
            "PRODUCE": "produce or repair artifact",
            "VERIFY": "run required verification",
            "REVIEW": "collect independent review",
            "CHALLENGE": "run challenge",
        }.get(state, "apply declared repair")
    elif blocking:
        decision = decisions[-1] if decisions else None
        state = "REPAIR"
        next_action = "repair open blocking/high findings"
    elif latest_artifact is None:
        decision = None
        state = "PRODUCE"
        next_action = "produce the first artifact"
    elif final_failed:
        decision = None
        state = "REPAIR"
        next_action = "repair failed verification evidence"
    elif final_pending:
        decision = None
        state = "VERIFY"
        next_action = "run required verification"
    elif tier in {"L2", "L3"} and not reviewer_pass:
        decision = None
        state = "REVIEW"
        next_action = "collect independent review"
    elif tier == "L3" and not challenger_pass:
        decision = None
        state = "CHALLENGE"
        next_action = "collect independent challenge"
    elif tier == "L3" and not human_approval:
        decision = None
        state = "RECONCILE"
        next_action = "obtain exact-version human approval"
    elif (latest_terminal is not None
          and latest_terminal.get("decision") == "ACCEPT"):
        decision = latest_terminal
        state = "ACCEPT"
        next_action = "none"
    else:
        decision = None
        state = "DECIDE"
        next_action = "record the Decision"
    return {
        "schema_version": 1,
        "checkpoint_id": "CKPT-{}-{}".format(
            datetime.datetime.now().astimezone().strftime(
                "%Y%m%d-%H%M%S-%f"),
            uuid.uuid4().hex[:8]),
        "created_at": datetime.datetime.now().astimezone().isoformat(),
        "records_digest": digest,
        "work_item_id": work_item.get("id"),
        "state": state,
        "next_action": next_action,
        "artifact_versions": sorted(
            (record.get("version") for record in artifacts),
            key=version_key),
        "open_findings": open_findings,
        "last_decision": (
            decision.get("id") if isinstance(decision, dict) else None),
        "source": "canonical_records",
    }


def checkpoint_errors(checkpoint):
    if not isinstance(checkpoint, dict):
        return ["checkpoint must be an object"]
    errors = []
    if checkpoint.get("schema_version") != 1:
        errors.append("checkpoint schema_version must be 1")
    checkpoint_id = checkpoint.get("checkpoint_id")
    if (not isinstance(checkpoint_id, str)
            or not re.fullmatch(r"CKPT-[A-Za-z0-9._-]+", checkpoint_id)):
        errors.append("checkpoint_id is invalid")
    for field in ("created_at", "next_action"):
        if (not isinstance(checkpoint.get(field), str)
                or not checkpoint.get(field).strip()):
            errors.append("{} must be non-blank".format(field))
    digest = checkpoint.get("records_digest")
    if not isinstance(digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", digest):
        errors.append("records_digest is invalid")
    if (not isinstance(checkpoint.get("work_item_id"), str)
            or not STABLE_ID.fullmatch(checkpoint.get("work_item_id", ""))):
        errors.append("work_item_id is invalid")
    if checkpoint.get("state") not in {
            "DEFINE", "PRODUCE", "VERIFY", "REVIEW", "CHALLENGE",
            "RECONCILE", "DECIDE", "REPAIR", "ACCEPT", "ESCALATE", "STOP"}:
        errors.append("state is invalid")
    versions = checkpoint.get("artifact_versions")
    if (not isinstance(versions, list)
            or not all(isinstance(item, str) and item for item in versions)):
        errors.append("artifact_versions is invalid")
    findings = checkpoint.get("open_findings")
    if (not isinstance(findings, list)
            or not all(
                isinstance(item, str) and STABLE_ID.fullmatch(item)
                for item in findings)):
        errors.append("open_findings is invalid")
    return errors


def checkpoint_semantic_errors(checkpoint, records, digest):
    expected = derive_runtime_state(records, digest)
    errors = []
    for field in (
            "records_digest", "work_item_id", "state", "next_action",
            "artifact_versions", "open_findings", "last_decision"):
        if checkpoint.get(field) != expected.get(field):
            errors.append("checkpoint {} does not match records".format(field))
    return errors


def write_checkpoint(store, checkpoint):
    root = Path(store).resolve()
    checkpoints = root / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    target = checkpoints / "{}.json".format(checkpoint["checkpoint_id"])
    temporary = target.with_name(
        ".{}.{}.tmp".format(target.name, uuid.uuid4().hex))
    temporary.write_text(
        json.dumps(checkpoint, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    os.replace(str(temporary), str(target))
    return target


def checkpoint_store_path(records, store):
    records = Path(records).resolve()
    store = Path(store).resolve()
    try:
        common = Path(os.path.commonpath((str(records), str(store))))
    except ValueError:
        return store
    if common == records:
        raise ValueError("runtime store must not be inside the records directory")
    return store


def external_output_path(records, output):
    if output is None:
        return None
    records = Path(records).resolve()
    output = Path(output).resolve()
    try:
        common = Path(os.path.commonpath((str(records), str(output))))
    except ValueError:
        return output
    if common == records:
        raise ValueError(
            "output must not be inside the records directory")
    return output


def valid_checkpoints(store):
    root = Path(store).resolve() / "checkpoints"
    checkpoints = []
    skipped = 0
    if not root.is_dir():
        return checkpoints, skipped
    for path in sorted(root.glob("*.json"), reverse=True):
        try:
            checkpoint = load_json(path)
        except ValueError:
            skipped += 1
            continue
        if checkpoint_errors(checkpoint):
            skipped += 1
            continue
        checkpoints.append(checkpoint)
    return checkpoints, skipped


def runtime_checkpoint(records_dir, store):
    try:
        store = checkpoint_store_path(records_dir, store)
        _, records = load_runtime_records(records_dir)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    errors = runtime_record_errors(records)
    if errors:
        print("[FAIL] runtime records", file=sys.stderr)
        for error in errors:
            print("ERROR: {}".format(json.dumps(error, ensure_ascii=True)),
                  file=sys.stderr)
        return 1
    checkpoint = derive_runtime_state(records, records_sha256(records))
    write_checkpoint(store, checkpoint)
    print(json.dumps(checkpoint, indent=2, ensure_ascii=False))
    return 0


def runtime_status(store, records_dir=None):
    if records_dir:
        try:
            store = checkpoint_store_path(records_dir, store)
        except ValueError as exc:
            print("ERROR: {}".format(exc), file=sys.stderr)
            return 2
    checkpoints, skipped = valid_checkpoints(store)
    checkpoint = checkpoints[0] if checkpoints else None
    if records_dir:
        try:
            _, records = load_runtime_records(records_dir)
        except ValueError as exc:
            print("ERROR: {}".format(exc), file=sys.stderr)
            return 2
        digest = records_sha256(records)
        matching = next(
            (item for item in checkpoints
             if item.get("records_digest") == digest), None)
        if matching is not None and checkpoint_semantic_errors(
                matching, records, digest):
            matching = None
            skipped += 1
        if matching is None:
            errors = runtime_record_errors(records)
            if errors:
                print("ERROR: no matching checkpoint and records are invalid",
                      file=sys.stderr)
                return 1
            checkpoint = derive_runtime_state(records, digest)
            checkpoint["source"] = "canonical_records_recovery"
        else:
            checkpoint = matching
    elif checkpoint is None:
        print("ERROR: no valid runtime checkpoint found", file=sys.stderr)
        return 1
    result = dict(checkpoint, skipped_invalid=skipped)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def runtime_resume(store, records_dir=None):
    if records_dir:
        try:
            store = checkpoint_store_path(records_dir, store)
        except ValueError as exc:
            print("ERROR: {}".format(exc), file=sys.stderr)
            return 2
    checkpoints, skipped = valid_checkpoints(store)
    if not records_dir:
        if not checkpoints:
            print("ERROR: no valid runtime checkpoint found", file=sys.stderr)
            return 1
        print(json.dumps({
            "checkpoint": checkpoints[0],
            "recovered": skipped > 0,
            "skipped_invalid": skipped,
        }, indent=2, ensure_ascii=False))
        return 0
    try:
        _, records = load_runtime_records(records_dir)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    errors = runtime_record_errors(records)
    if errors:
        print("[FAIL] runtime records", file=sys.stderr)
        for error in errors:
            print("ERROR: {}".format(json.dumps(error, ensure_ascii=True)),
                  file=sys.stderr)
        return 1
    digest = records_sha256(records)
    matching = next(
        (item for item in checkpoints
         if item.get("records_digest") == digest), None)
    if matching is not None and checkpoint_semantic_errors(
            matching, records, digest):
        matching = None
        skipped += 1
    recovered = matching is None
    if matching is None:
        matching = derive_runtime_state(records, digest)
        matching["source"] = "canonical_records_recovery"
        if checkpoints:
            matching["recovered_from"] = checkpoints[0]["checkpoint_id"]
        write_checkpoint(store, matching)
    print(json.dumps({
        "checkpoint": matching,
        "recovered": recovered or skipped > 0,
        "skipped_invalid": skipped,
    }, indent=2, ensure_ascii=False))
    return 0


def approve_records(records_dir, artifact_path, approver, statement,
                    confirmation):
    try:
        root, records = load_runtime_records(records_dir)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    errors = runtime_record_errors(records, accept_gate=False)
    if errors:
        print("[FAIL] approval records", file=sys.stderr)
        for error in errors:
            print("ERROR: {}".format(json.dumps(error, ensure_ascii=True)),
                  file=sys.stderr)
        return 1
    artifact_path = Path(artifact_path).resolve()
    try:
        if Path(os.path.commonpath((str(root), str(artifact_path)))) != root:
            raise ValueError("artifact must be inside the records directory")
        artifact = load_json(artifact_path)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    if artifact.get("kind") != "artifact":
        print("ERROR: approval target must be an Artifact", file=sys.stderr)
        return 2
    work_item = next(
        record for record in records if record.get("kind") == "work_item")
    final_artifact, lineage_errors = lineage_final_artifact(records)
    if lineage_errors:
        print(
            "ERROR: approval requires unambiguous final Artifact lineage: {}".format(
                "; ".join(lineage_errors)),
            file=sys.stderr)
        return 1
    if (work_item.get("control_tier") != "L3"
            or final_artifact is None
            or artifact.get("id") != final_artifact.get("id")
            or artifact.get("version") != final_artifact.get("version")
            or artifact.get("content_hash")
            != final_artifact.get("content_hash")):
        print(
            "ERROR: approval target must be the final L3 Artifact",
            file=sys.stderr)
        return 1
    missing = [
        role for role, ready in (
            ("reviewer", role_pass_exists(records, artifact, "reviewer")),
            ("challenger", role_pass_exists(records, artifact, "challenger")),
        ) if not ready
    ]
    if missing:
        print(
            "ERROR: approval requires final-version PASS evidence for {}".format(
                ", ".join(missing)),
            file=sys.stderr)
        return 1
    criteria = set(work_item.get("acceptance_criteria", {}))
    verifier_coverage = {
        criterion_id
        for record in records
        if record.get("kind") == "verification"
        and record.get("artifact_id") == artifact.get("id")
        and record.get("artifact_version") == artifact.get("version")
        and record.get("role") == "verifier"
        and record.get("status") == "PASS"
        and not record.get("closure_gate")
        for criterion_id in record.get("criterion_ids", [])
    }
    uncovered = sorted(criteria - verifier_coverage)
    if uncovered:
        print(
            "ERROR: approval requires Verifier coverage for {}".format(
                ", ".join(uncovered)),
            file=sys.stderr)
        return 1
    blocking = [
        record for record in records
        if record.get("kind") == "finding"
        and record.get("status") == "open"
        and record.get("severity") in {"high", "blocking"}
    ]
    if blocking:
        print(
            "ERROR: approval blocked by open high/blocking findings: {}".format(
                ", ".join(record["id"] for record in blocking)),
            file=sys.stderr)
        return 1
    final_evidence = [
        record for record in records
        if record.get("kind") == "verification"
        and record.get("artifact_id") == artifact.get("id")
        and record.get("artifact_version") == artifact.get("version")
        and record.get("status") == "PASS"
        and record.get("role") in {"verifier", "reviewer", "challenger"}
        and not record.get("closure_gate")
    ]
    execution_failures = [
        error for record in final_evidence
        for error in execution_errors(record)
    ]
    finding_failures = []
    all_verifications = [
        record for record in records
        if record.get("kind") == "verification"
    ]
    for finding in records:
        if (finding.get("kind") != "finding"
                or finding.get("status") not in {
                    "resolved", "not_reproducible"}
                or (
                    finding.get("severity") not in {"high", "blocking"}
                    and not finding.get("recurrence_of"))):
            continue
        finding_failures.extend(verification_errors(
            finding, work_item, final_artifact, all_verifications,
            pre_closure=True))
    source_failures = artifact_source_errors(final_artifact, Path.cwd())
    failures = execution_failures + finding_failures + source_failures
    if failures:
        print("[FAIL] approval preconditions", file=sys.stderr)
        for error in failures:
            print("ERROR: {}".format(json.dumps(error, ensure_ascii=True)),
                  file=sys.stderr)
        return 1
    expected = "APPROVE {}@{}".format(
        artifact.get("id"), artifact.get("version"))
    if confirmation != expected:
        print("ERROR: confirmation must equal {}".format(
            json.dumps(expected)), file=sys.stderr)
        return 2
    if not isinstance(approver, str) or not approver.strip() or (
            approver.strip().lower() == "controller"):
        print("ERROR: --approver must identify a human", file=sys.stderr)
        return 2
    if not isinstance(statement, str) or not statement.strip():
        print("ERROR: --statement must be non-blank", file=sys.stderr)
        return 2
    reviewed_set_digest = reviewed_set_sha256(records, artifact)
    approval = {
        "schema_version": 3,
        "id": "AP-{}-{}".format(
            datetime.datetime.now().astimezone().strftime(
                "%Y%m%d-%H%M%S-%f"),
            uuid.uuid4().hex[:8]),
        "kind": "approval",
        "work_item_id": work_item.get("id"),
        "artifact_id": artifact.get("id"),
        "artifact_version": artifact.get("version"),
        "artifact_content_hash": artifact.get("content_hash"),
        "reviewed_set_digest": reviewed_set_digest,
        "approver": approver.strip(),
        "statement": statement.strip(),
        "approved_at": datetime.datetime.now().astimezone().isoformat(),
        "confirmation": confirmation,
        "authentication": "unverified_host_attestation",
    }
    schema = load_json(SCHEMA_ROOT / SCHEMA_FILES["approval"])
    approval_errors = schema_errors(approval, schema)
    if approval_errors:
        print("[FAIL] approval", file=sys.stderr)
        for error in approval_errors:
            print("ERROR: {}".format(json.dumps(error, ensure_ascii=True)),
                  file=sys.stderr)
        return 1
    target = root / "approval-{}.json".format(uuid.uuid4().hex[:12])
    temporary = target.with_name(
        ".{}.{}.tmp".format(target.name, uuid.uuid4().hex))
    temporary.write_text(
        json.dumps(approval, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    os.replace(str(temporary), str(target))
    print(json.dumps(approval, indent=2, ensure_ascii=False))
    return 0


def load_host_metrics(path):
    if path is None:
        return {}
    value = load_json(path)
    allowed = {
        "turns", "tool_calls", "total_tokens", "cost_usd",
        "elapsed_seconds",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError("host metrics unknown fields: {}".format(
            _quoted_names(unknown)))
    for key, item in value.items():
        if (isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(item) or item < 0):
            raise ValueError(
                "host metric {} must be a non-negative number".format(key))
    return value


def metrics_data(records, host_metrics=None):
    digest = records_sha256(records)
    runtime = derive_runtime_state(records, digest)
    verification_statuses = {
        status: 0 for status in ("PASS", "FAIL", "BLOCKED", "NOT_RUN")
    }
    findings_by_status = {}
    findings_by_severity = {}
    for record in records:
        if record.get("kind") == "verification":
            status = record.get("status")
            if status in verification_statuses:
                verification_statuses[status] += 1
        elif record.get("kind") == "finding":
            status = record.get("status")
            if status in {
                    "open", "resolved", "accepted_risk",
                    "not_reproducible"}:
                findings_by_status[status] = (
                    findings_by_status.get(status, 0) + 1)
            severity = record.get("severity")
            if severity in {"low", "medium", "high", "blocking"}:
                findings_by_severity[severity] = (
                    findings_by_severity.get(severity, 0) + 1)
    decisions = [
        record for record in records if record.get("kind") == "decision"
    ]
    iterations = [
        record for record in records if record.get("kind") == "iteration"
    ]
    return {
        "schema_version": 1,
        "work_item_id": runtime["work_item_id"],
        "record_count": len(records),
        "records_digest": digest,
        "state": runtime["state"],
        "artifact_versions": runtime["artifact_versions"],
        "decision_count": len(decisions),
        "terminal_decision": next(
            (record.get("decision") for record in reversed(decisions)
             if record.get("decision") in {"ACCEPT", "STOP", "ESCALATE"}),
            None),
        "iteration_count": len(iterations),
        "repair_iterations": sum(
            record.get("result") == "REPAIR" for record in iterations),
        "approval_count": sum(
            record.get("kind") == "approval" for record in records),
        "open_findings": runtime["open_findings"],
        "findings_by_status": findings_by_status,
        "findings_by_severity": findings_by_severity,
        "verification_statuses": verification_statuses,
        "host_metrics": host_metrics or {},
    }


def metrics(records_dir, host_metrics_path=None, output=None):
    try:
        output = external_output_path(records_dir, output)
        _, records = load_runtime_records(records_dir)
        host = load_host_metrics(host_metrics_path)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    errors = runtime_record_errors(records)
    if errors:
        print("[FAIL] metrics records", file=sys.stderr)
        for error in errors:
            print("ERROR: {}".format(json.dumps(error, ensure_ascii=True)),
                  file=sys.stderr)
        return 1
    data = metrics_data(records, host)
    if output:
        write_json_file(output, data)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def candidate_id(category, evidence_refs):
    encoded = json.dumps(
        [category, sorted(evidence_refs)],
        sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "IMP-{}".format(hashlib.sha256(encoded).hexdigest()[:12].upper())


def improvement_candidates(records):
    candidates = []

    def add(category, priority, evidence_refs, action):
        evidence_refs = sorted(evidence_refs)
        candidates.append({
            "id": candidate_id(category, evidence_refs),
            "category": category,
            "priority": priority,
            "evidence_refs": evidence_refs,
            "action": action,
            "source": "canonical_records",
        })

    findings = [
        record for record in records if record.get("kind") == "finding"
    ]
    for finding in findings:
        if finding.get("recurrence_of"):
            add(
                "recurring_finding", "high", [finding.get("id")],
                "Replace the repeated correction with a structural guard.")
        elif (finding.get("severity") == "medium"
              and finding.get("status") in {"open", "accepted_risk"}):
            add(
                "resolve_medium_finding", "medium", [finding.get("id")],
                "Repair the bounded risk or record explicit residual ownership.")
        prevention = finding.get("prevention")
        if (finding.get("severity") in {"high", "blocking"}
                and isinstance(prevention, dict)
                and prevention.get("kind") in {
                    "automatic_check", "skill_rule", "human_review"}):
            add(
                "prefer_structural_prevention", "low", [finding.get("id")],
                "Prefer a structural guard over repeat-only prevention.")
    failed = [
        record for record in records
        if record.get("kind") == "verification"
        and record.get("status") in {"FAIL", "BLOCKED", "NOT_RUN"}
    ]
    for verification in failed:
        add(
            "stabilize_check", "high", [verification.get("id")],
            "Make the check deterministic or restore its required dependency.")
    iterations = [
        record for record in records if record.get("kind") == "iteration"
    ]
    repairs = [
        record for record in iterations if record.get("result") == "REPAIR"
    ]
    if len(repairs) >= 2:
        add(
            "reduce_repair_cycles", "medium",
            [record.get("id") for record in repairs],
            "Find the shared root cause behind repeated repairs.")
    rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        candidates,
        key=lambda item: (
            rank.get(item["priority"], 3), item["category"], item["id"]))


def improvements(records_dir, output=None):
    try:
        output = external_output_path(records_dir, output)
        _, records = load_runtime_records(records_dir)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    errors = runtime_record_errors(records)
    if errors:
        print("[FAIL] improvement records", file=sys.stderr)
        for error in errors:
            print("ERROR: {}".format(json.dumps(error, ensure_ascii=True)),
                  file=sys.stderr)
        return 1
    data = {
        "schema_version": 1,
        "candidates": improvement_candidates(records),
    }
    if output:
        write_json_file(output, data)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def registry_entry_errors(entry):
    errors = []
    if entry.get("schema_version") != 1:
        errors.append("registry entry schema_version must be 1")
    if (not isinstance(entry.get("work_item_id"), str)
            or not STABLE_ID.fullmatch(entry.get("work_item_id", ""))):
        errors.append("registry entry work_item_id is invalid")
    digest = entry.get("records_digest")
    if not isinstance(digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", digest):
        errors.append("registry entry records_digest is invalid")
    versions = entry.get("artifact_versions")
    if (not isinstance(versions, list) or not versions
            or not all(
                isinstance(item, str) and item.strip() for item in versions)):
        errors.append("registry entry artifact_versions is invalid")
    if entry.get("state") not in {
            "DEFINE", "PRODUCE", "VERIFY", "REVIEW", "CHALLENGE",
            "RECONCILE", "DECIDE", "REPAIR", "ACCEPT", "ESCALATE", "STOP"}:
        errors.append("registry entry state is invalid")
    approval_count = entry.get("approval_count")
    if (isinstance(approval_count, bool)
            or not isinstance(approval_count, int)
            or approval_count < 0):
        errors.append("registry entry approval_count is invalid")
    for field in ("label", "commit"):
        if not isinstance(entry.get(field), str):
            errors.append("registry entry {} is invalid".format(field))
    registered_at = entry.get("registered_at")
    if not isinstance(registered_at, str):
        errors.append("registry entry registered_at is invalid")
    else:
        try:
            datetime.datetime.fromisoformat(registered_at)
        except ValueError:
            errors.append("registry entry registered_at is invalid")
    return errors


def registry_provenance(entry):
    return {
        field: entry.get(field) for field in (
            "schema_version", "work_item_id", "records_digest",
            "artifact_versions", "state", "approval_count", "label", "commit")
    }


def write_registry_entry(path, entry):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        ".{}.{}.tmp".format(path.name, uuid.uuid4().hex))
    temporary.write_text(
        json.dumps(entry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    try:
        os.link(str(temporary), str(path))
        return entry
    except FileExistsError:
        existing = load_json(path)
        if registry_provenance(existing) != registry_provenance(entry):
            raise ValueError("registry provenance conflict")
        return existing
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def registry_update(store, records_dir, label=None, commit=None):
    try:
        store = checkpoint_store_path(records_dir, store)
        _, records = load_runtime_records(records_dir)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    errors = runtime_record_errors(records)
    if errors:
        print("[FAIL] registry records", file=sys.stderr)
        for error in errors:
            print("ERROR: {}".format(json.dumps(error, ensure_ascii=True)),
                  file=sys.stderr)
        return 1
    digest = records_sha256(records)
    runtime = derive_runtime_state(records, digest)
    entry = {
        "schema_version": 1,
        "work_item_id": runtime["work_item_id"],
        "records_digest": digest,
        "artifact_versions": runtime["artifact_versions"],
        "state": runtime["state"],
        "approval_count": sum(
            record.get("kind") == "approval" for record in records),
        "label": label or "",
        "commit": commit or "",
        "registered_at": datetime.datetime.now().astimezone().isoformat(),
    }
    key = "{}\0{}".format(entry["work_item_id"], digest).encode("utf-8")
    filename = "{}.json".format(hashlib.sha256(key).hexdigest())
    path = Path(store).resolve() / "registry" / "runs" / filename
    try:
        entry = write_registry_entry(path, entry)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    return 0


def registry_list(store):
    root = Path(store).resolve()
    runs = []
    for path in sorted((root / "registry" / "runs").glob("*.json")):
        try:
            entry = load_json(path)
        except ValueError as exc:
            print("ERROR: {}".format(exc), file=sys.stderr)
            return 1
        errors = registry_entry_errors(entry)
        if errors:
            print("ERROR: {}".format(errors[0]), file=sys.stderr)
            return 1
        runs.append(entry)
    legacy = root / "registry.json"
    if legacy.exists():
        try:
            old = load_json(legacy)
        except ValueError as exc:
            print("ERROR: {}".format(exc), file=sys.stderr)
            return 1
        if isinstance(old.get("runs"), list):
            for entry in old["runs"]:
                if not isinstance(entry, dict):
                    print(
                        "ERROR: legacy registry run must be an object",
                        file=sys.stderr)
                    return 1
                runs.append(entry)
    unique = {}
    for entry in runs:
        errors = registry_entry_errors(entry)
        if errors:
            print("ERROR: {}".format(errors[0]), file=sys.stderr)
            return 1
        key = (entry["work_item_id"], entry["records_digest"])
        if key in unique:
            if registry_provenance(unique[key]) != registry_provenance(entry):
                print("ERROR: registry provenance conflict", file=sys.stderr)
                return 1
            continue
        unique[key] = entry
    registry = {
        "schema_version": 1,
        "runs": sorted(
            unique.values(),
            key=lambda entry: (
                entry.get("work_item_id", ""),
                entry.get("registered_at", ""))),
    }
    print(json.dumps(registry, indent=2, ensure_ascii=False))
    return 0


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
    common_paths = (
        "core/protocol.md",
        "core/state-machine.md",
        "core/decision-policy.md",
        "core/artifact-schema/work-item.schema.json",
        "core/artifact-schema/artifact.schema.json",
        "core/artifact-schema/finding.schema.json",
        "core/artifact-schema/verification.schema.json",
        "core/artifact-schema/decision.schema.json",
        "core/artifact-schema/iteration.schema.json",
        "core/artifact-schema/approval.schema.json",
        "core/artifact-schema/README.md",
        "core/artifact-schema/migrations/v2-to-v3.json",
        "roles/producer.md",
        "roles/verifier.md",
        "roles/reviewer.md",
        "roles/challenger.md",
        "roles/arbiter.md",
        "workflows/iterative-delivery/workflow.md",
        "workflows/adversarial-review/workflow.md",
        "workflows/continuous-improvement/workflow.md",
        "packs/software-development/pack.md",
        "packs/software-development/verification-skill.md",
        "packs/architecture-design/pack.md",
        "loop_engineering/cli.py",
    )
    if mode == "installed":
        print("Config: not used in installed mode")
        required_paths = ("SKILL.md",) + common_paths
        missing = []
        missing_label = "installed path(s)"
    else:
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
        required_paths = (
            "AGENTS.md",
            "CLAUDE.md",
        ) + common_paths + (
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
        )
        missing_label = "required kit path(s)"
    for name in required_paths:
        present = (root / name).is_file()
        print("{}: {}".format(name, "present" if present else "missing"))
        if not present:
            missing.append(name)
    if missing:
        print("ERROR: {} {} missing".format(len(missing), missing_label))
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
                           encoding="utf-8", errors="replace",
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


def route_plan(risk, files, trivial=False, ambiguous=False, irreversible=False,
               max_repairs=None):
    common_stops = [
        "acceptance criteria have passing evidence",
        "the same failure fingerprint repeats without new evidence",
        "the repair budget is exhausted",
        "required evidence is BLOCKED or unavailable",
    ]
    if risk in ("high", "critical") or irreversible:
        data = {
            "tier": "L3",
            "roles": ["producer", "verifier", "reviewer", "challenger",
                      "arbiter"],
            "review_independence": "independent",
            "max_repair_iterations": 3,
            "human_approval_required": True,
            "record_depth": "audited",
        }
    elif ambiguous or files > 1 or risk == "medium":
        data = {
            "tier": "L2",
            "roles": ["producer", "verifier", "reviewer", "arbiter"],
            "review_independence": "independent",
            "max_repair_iterations": 3,
            "human_approval_required": False,
            "record_depth": "full",
        }
    elif trivial and files <= 1:
        data = {
            "tier": "L0",
            "roles": [],
            "review_independence": "not_required",
            "max_repair_iterations": 0,
            "human_approval_required": False,
            "record_depth": "none",
        }
    else:
        data = {
            "tier": "L1",
            "roles": ["producer", "verifier", "arbiter"],
            "review_independence": "non_independent",
            "max_repair_iterations": 2,
            "human_approval_required": False,
            "record_depth": "compact",
        }
    data["stop_conditions"] = common_stops
    if data["tier"] == "L3":
        data["stop_conditions"].append(
            "human approval is missing before an irreversible action")
    if max_repairs is not None:
        data["max_repair_iterations"] = max_repairs
    return data


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
    run_id = "{}-{}".format(
        started.strftime("%Y%m%d-%H%M%S-%f-%z"), uuid.uuid4().hex[:8])
    data = {"schema_version": 1, "run_id": run_id,
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
    d.add_argument("--mode", choices=("kit", "project", "installed"), default="kit")
    v = subs.add_parser("verify")
    v.add_argument("--root", default=".")
    v.add_argument("--config", default=None)
    v.add_argument("--report-dir", default=None)
    v.add_argument("--timeout", type=int, default=900)
    rte = subs.add_parser("route")
    rte.add_argument("--risk", choices=("low", "medium", "high", "critical"),
                     default="low")
    rte.add_argument("--files", type=int, default=1)
    rte.add_argument("--trivial", action="store_true")
    rte.add_argument("--ambiguous", action="store_true")
    rte.add_argument("--irreversible", action="store_true")
    rte.add_argument("--max-repairs", type=int, default=None)
    cf = subs.add_parser("check-finding")
    cf.add_argument("--input", required=True)
    cf.add_argument("--work-item", default=None)
    cf.add_argument("--artifact", default=None)
    cf.add_argument("--verifications-dir", default=None)
    cr = subs.add_parser("check-records")
    cr.add_argument("--dir", required=True)
    cr.add_argument("--repo", default=None)
    cr.add_argument("--pre-closure", action="store_true")
    mr = subs.add_parser("migrate-records")
    mr.add_argument("--dir", required=True)
    mr.add_argument("--write", action="store_true")
    mr.add_argument("--verification-role", action="append", default=[])
    mr.add_argument("--record-criteria", action="append", default=[])
    mr.add_argument("--execution-evidence", default=None)
    rc = subs.add_parser("runtime-checkpoint")
    rc.add_argument("--records", required=True)
    rc.add_argument("--store", required=True)
    rs = subs.add_parser("runtime-status")
    rs.add_argument("--store", required=True)
    rs.add_argument("--records", required=True)
    rr = subs.add_parser("runtime-resume")
    rr.add_argument("--store", required=True)
    rr.add_argument("--records", required=True)
    ap = subs.add_parser("approve")
    ap.add_argument("--records", required=True)
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--approver", required=True)
    ap.add_argument("--statement", required=True)
    ap.add_argument("--confirm", required=True)
    met = subs.add_parser("metrics")
    met.add_argument("--dir", required=True)
    met.add_argument("--host-metrics", default=None)
    met.add_argument("--output", default=None)
    imp = subs.add_parser("improvements")
    imp.add_argument("--dir", required=True)
    imp.add_argument("--output", default=None)
    ru = subs.add_parser("registry-update")
    ru.add_argument("--store", required=True)
    ru.add_argument("--records", required=True)
    ru.add_argument("--label", default=None)
    ru.add_argument("--commit", default=None)
    rl = subs.add_parser("registry-list")
    rl.add_argument("--store", required=True)
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
    if a.command == "route":
        if a.files < 0:
            p.error("--files must be non-negative")
        if a.max_repairs is not None and a.max_repairs < 0:
            p.error("--max-repairs must be non-negative")
        print(json.dumps(route_plan(
            a.risk, a.files, a.trivial, a.ambiguous, a.irreversible,
            a.max_repairs),
            indent=2, ensure_ascii=False))
        return 0
    if a.command == "check-finding":
        return check_finding(
            a.input, a.work_item, a.artifact, a.verifications_dir)
    if a.command == "check-records":
        return check_records(a.dir, a.repo, a.pre_closure)
    if a.command == "migrate-records":
        return migrate_records(
            a.dir, a.write, a.verification_role, a.record_criteria,
            a.execution_evidence)
    if a.command == "runtime-checkpoint":
        return runtime_checkpoint(a.records, a.store)
    if a.command == "runtime-status":
        return runtime_status(a.store, a.records)
    if a.command == "runtime-resume":
        return runtime_resume(a.store, a.records)
    if a.command == "approve":
        return approve_records(
            a.records, a.artifact, a.approver, a.statement, a.confirm)
    if a.command == "metrics":
        return metrics(a.dir, a.host_metrics, a.output)
    if a.command == "improvements":
        return improvements(a.dir, a.output)
    if a.command == "registry-update":
        return registry_update(
            a.store, a.records, a.label, a.commit)
    if a.command == "registry-list":
        return registry_list(a.store)
    try:
        data = load_json(a.input)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, ensure_ascii=False) if a.format == "json" else markdown(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
