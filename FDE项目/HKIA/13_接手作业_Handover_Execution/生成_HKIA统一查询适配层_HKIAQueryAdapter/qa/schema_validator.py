"""递归 JSON Schema 类型校验器（等价递归校验，因环境无 jsonschema 库）。
只实现本 Schema 用到的 required/type/properties 语义。"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple


def _type_ok(schema_type, value) -> bool:
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "null":
        return value is None
    return True


def _schema_allows_null(schema) -> bool:
    t = schema.get("type")
    if isinstance(t, list):
        return "null" in t
    return t == "null"


def validate(obj: Any, schema: Dict) -> List[str]:
    """递归校验 obj 是否符合 schema，返回错误列表（空=通过）。"""
    errors = []
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        # union type: 只要匹配任一即可
        if not any(_type_ok(t, obj) for t in schema_type):
            errors.append(f"type mismatch: expected {schema_type}, got {type(obj).__name__}")
    elif schema_type and not _type_ok(schema_type, obj):
        errors.append(f"type mismatch: expected {schema_type}, got {type(obj).__name__}")
    # required check (objects only)
    if schema_type == "object" or isinstance(schema_type, list) and "object" in schema_type:
        if obj is not None and isinstance(obj, dict):
            required = schema.get("required", [])
            missing = [r for r in required if r not in obj]
            if missing:
                errors.append(f"missing required: {missing}")
            props = schema.get("properties", {})
            for k, subschema in props.items():
                if k in obj:
                    errors.extend([f"{k}.{e}" for e in validate(obj[k], subschema)])
        # 额外属性检查（可选，本 Schema 未设 additionalProperties:false，不阻断）
    elif schema_type == "array" and isinstance(obj, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(obj):
                errors.extend([f"[{i}].{e}" for e in validate(item, items_schema)])
    return errors
