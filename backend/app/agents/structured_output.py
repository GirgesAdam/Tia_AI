from __future__ import annotations

from copy import deepcopy
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ValidationError

from app.agents.llm_runtime import LLMProviderError, invoke_model

T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(RuntimeError):
    pass


class StructuredOutputSchemaCompatibilityError(RuntimeError):
    pass


# Local Pydantic validation keywords that are intentionally not sent to Gemini.
# Tia re-validates the returned payload using the original Pydantic model.
_GEMINI_LOCAL_ONLY_SCHEMA_KEYS = frozenset(
    {
        "default",
        "examples",
        "pattern",
        "minLength",
        "maxLength",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "const",
    }
)


def canonicalize_gemini_json_schema(
    schema: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert Pydantic JSON Schema to Gemini's documented structured-output subset.

    Transformations:
    - inline local `#/$defs/...` references;
    - remove `$defs` / `$ref`;
    - convert nullable `anyOf` to `type: [<type>, "null"]`;
    - remove local-only validation keywords.

    General unions are rejected rather than silently weakened. Tia's provider
    schemas should use enums and nullable fields, not arbitrary unions.
    """
    root = deepcopy(schema)
    definitions = root.get("$defs", {})

    def resolve_reference(ref: str, stack: tuple[str, ...]) -> dict[str, Any]:
        prefix = "#/$defs/"
        if not ref.startswith(prefix):
            raise StructuredOutputSchemaCompatibilityError(
                f"Unsupported external JSON Schema reference: {ref}"
            )
        name = ref[len(prefix):]
        if name not in definitions:
            raise StructuredOutputSchemaCompatibilityError(
                f"Unknown JSON Schema definition: {name}"
            )
        if name in stack:
            raise StructuredOutputSchemaCompatibilityError(
                f"Recursive JSON Schema definition is not supported: {name}"
            )
        resolved = walk(deepcopy(definitions[name]), (*stack, name))
        if not isinstance(resolved, dict):
            raise StructuredOutputSchemaCompatibilityError(
                f"Definition {name} did not resolve to an object schema."
            )
        return resolved

    def nullable_any_of(
        node: dict[str, Any],
        stack: tuple[str, ...],
    ) -> dict[str, Any]:
        branches = node.get("anyOf")
        if not isinstance(branches, list):
            raise StructuredOutputSchemaCompatibilityError(
                "JSON Schema anyOf must be an array."
            )

        null_indexes = [
            index
            for index, branch in enumerate(branches)
            if isinstance(branch, dict)
            and branch.get("type") == "null"
            and set(branch.keys()) <= {"type", "title", "description"}
        ]
        non_null = [
            branch
            for index, branch in enumerate(branches)
            if index not in null_indexes
        ]

        if len(null_indexes) != 1 or len(non_null) != 1:
            raise StructuredOutputSchemaCompatibilityError(
                "Gemini provider schema contains a non-nullable anyOf union."
            )

        base = walk(non_null[0], stack)
        if not isinstance(base, dict) or "type" not in base:
            raise StructuredOutputSchemaCompatibilityError(
                "Nullable schema branch must resolve to a typed schema."
            )

        current_type = base["type"]
        type_values = (
            list(current_type)
            if isinstance(current_type, list)
            else [current_type]
        )
        if "null" not in type_values:
            type_values.append("null")
        base["type"] = type_values

        for key, value in node.items():
            if (
                key == "anyOf"
                or key in _GEMINI_LOCAL_ONLY_SCHEMA_KEYS
                or key == "$defs"
            ):
                continue
            base[key] = walk(value, stack)
        return base

    def walk(value: Any, stack: tuple[str, ...] = ()) -> Any:
        if isinstance(value, list):
            return [walk(item, stack) for item in value]

        if not isinstance(value, dict):
            return value

        if "$ref" in value:
            ref = value["$ref"]
            resolved = resolve_reference(ref, stack)
            for key, sibling in value.items():
                if key == "$ref":
                    continue
                if key in _GEMINI_LOCAL_ONLY_SCHEMA_KEYS:
                    continue
                resolved[key] = walk(sibling, stack)
            return resolved

        if "anyOf" in value:
            return nullable_any_of(value, stack)

        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key == "$defs" or key in _GEMINI_LOCAL_ONLY_SCHEMA_KEYS:
                continue
            cleaned[key] = walk(item, stack)
        return cleaned

    result = walk(root)
    if not isinstance(result, dict):
        raise StructuredOutputSchemaCompatibilityError(
            "Root structured-output schema must be an object."
        )
    return result


# Backward-compatible name used by v0.16.2 tests/docs.
sanitize_gemini_json_schema = canonicalize_gemini_json_schema


def invoke_typed_structured_output(
    *,
    model: BaseChatModel,
    schema: type[T],
    messages: list[BaseMessage],
) -> T:
    """
    Gemini native JSON Schema generation followed by full local validation.

    There is no function-calling schema shim, regex parser, free-form JSON
    recovery, or keyword intent fallback.
    """
    provider_schema = canonicalize_gemini_json_schema(
        schema.model_json_schema()
    )
    structured = model.with_structured_output(
        schema=provider_schema,
        method="json_schema",
    )

    result = invoke_model(lambda: structured.invoke(messages))

    try:
        if isinstance(result, schema):
            return result
        return schema.model_validate(result)
    except (ValidationError, TypeError, ValueError) as exc:
        raise StructuredOutputError(
            "Gemini returned structured data that failed local validation."
        ) from exc
