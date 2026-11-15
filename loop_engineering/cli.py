#!/usr/bin/env python3
"""Cross-platform standard-library CLI for deterministic verification."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import re
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


def verification_errors(finding, work_item, artifact, verifications):
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
        "content", "source", "work_item_id", "files",
    }
    artifact_missing = sorted(artifact_required - set(artifact))
    if artifact_missing:
        errors.append(
            "Artifact missing fields: {}".format(_quoted_names(artifact_missing)))
    artifact_extra = sorted(set(artifact) - artifact_required)
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
            "criterion_ids", "check", "method", "status", "evidence",
            "limitations", "finding_id",
        }
        missing = sorted(required - set(verification))
        if missing:
            errors.append(
                "Verification {} missing fields: {}".format(
                    verification_id, _quoted_names(missing)))
        extra = sorted(set(verification) - required - {"role"})
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
        if verification.get("status") != "PASS":
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


def records_errors(records):
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
                "decision", "iteration"}:
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

    for kind in ("finding", "verification", "decision", "iteration"):
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
        artifact_ids.add(artifact_id)
        artifact_versions.add(version)
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

    final_artifact = None
    if len(final_versions) == 1:
        final_version = next(iter(final_versions))
        final_artifact = next(
            (artifact for artifact in artifacts
             if artifact.get("version") == final_version),
            None)
    for finding_id, finding in findings.items():
        if final_artifact is not None:
            errors.extend(verification_errors(
                finding, work_item, final_artifact,
                list(verifications.values())))

    decisions = groups.get("decision", [])
    if not decisions:
        errors.append("records must contain at least one Decision")
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
        refs = decision.get("evidence_refs")
        if isinstance(refs, list):
            for ref in refs:
                if ref not in findings and ref not in verifications:
                    errors.append(
                        "Decision evidence_ref {} does not resolve".format(
                            json.dumps(ref, ensure_ascii=True)))
                elif (ref in verifications
                      and verifications[ref].get("artifact_version")
                      not in versions):
                    errors.append(
                        "Decision evidence_ref {} targets a future Artifact version".format(
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
            ref_findings = [
                findings[ref] for ref in decision.get("evidence_refs", [])
                if ref in findings]
            ref_verifications = [
                verifications[ref] for ref in decision.get("evidence_refs", [])
                if ref in verifications]
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
            if control_tier == "L3" and not any(
                    finding.get("source_role") == "challenger"
                    for finding in ref_findings):
                errors.append(
                    "L3 ACCEPT requires referenced Challenger evidence")
            if (control_tier == "L3"
                    and (not isinstance(approver, str)
                         or approver.strip().lower() == "controller")):
                errors.append("L3 ACCEPT requires human approval")
            if control_tier == "L3":
                errors.append(
                    "BLOCKED: L3 ACCEPT requires verified human approval runtime")
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
                    if verification.get("status") != "PASS":
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
                    has_verifier_role = (
                        verification.get("role") == "verifier"
                        or (
                            verification.get("role") is None
                            and verification_id in legacy_roleless))
                    if (has_verifier_role
                            and verification.get("status") == "PASS"
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


def check_records(directory):
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
    errors = records_errors(records)
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
        return check_records(a.dir)
    try:
        data = load_json(a.input)
    except ValueError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, ensure_ascii=False) if a.format == "json" else markdown(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
