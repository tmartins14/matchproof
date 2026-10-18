"""Meta-validate every schema and validate examples against claim_graph.schema.json."""

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, SchemaError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "schemas"
EXAMPLES_DIR = SCHEMAS_DIR / "examples"


def load_schemas() -> dict[str, dict[str, object]]:
    schemas: dict[str, dict[str, object]] = {}
    for path in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        schemas[path.name] = json.loads(path.read_text())
    return schemas


def build_registry(
    schemas: dict[str, dict[str, object]],
) -> Registry[Any]:
    registry: Registry[Any] = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(
            str(schema["$id"]), Resource.from_contents(schema, DRAFT202012)
        )
    return registry


def main() -> int:
    schemas = load_schemas()
    errors: list[str] = []

    for name, schema in schemas.items():
        if "$id" not in schema:
            errors.append(f"{name}: missing $id")
            continue
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            errors.append(f"{name}: invalid schema: {exc}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    registry = build_registry(schemas)
    validator = Draft202012Validator(
        schemas["claim_graph.schema.json"], registry=registry
    )
    examples = sorted(EXAMPLES_DIR.glob("*.json"))
    for path in examples:
        for error in validator.iter_errors(json.loads(path.read_text())):
            location = "/".join(str(p) for p in error.absolute_path)
            errors.append(f"{path.name}: {location}: {error.message}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"ok: {len(schemas)} schemas, {len(examples)} examples")
    return 0


if __name__ == "__main__":
    sys.exit(main())
