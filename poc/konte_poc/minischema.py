# SPDX-License-Identifier: BSD-3-Clause
"""minischema —— 一个零依赖的 JSON Schema（Draft 2020-12 子集）校验器。

为什么不直接依赖 `jsonschema`：本 PoC 需在无第三方库的离线环境独立运行。
本实现覆盖 `konte.schema.json` 实际用到的关键字：
  $ref(#/$defs/...)、type、enum、const、required、properties、
  additionalProperties(bool)、items、minItems、minimum、pattern、
  format(date-time)、oneOf、anyOf、allOf。

对未支持的关键字（如 oneOf 中较复杂的组合）给出保守处理并明确列出。
生产 CI 建议仍接官方 `jsonschema` 做权威校验；本模块用于本地自检与 Bridge 快速反馈。
"""

from __future__ import annotations

import re
from datetime import datetime

_TRUE_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
}


def _type_ok(value, tname: str) -> bool:
    if tname == "null":
        return value is None
    if tname == "integer":
        # bool 是 int 的子类，需排除
        return isinstance(value, int) and not isinstance(value, bool)
    if tname == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if tname == "boolean":
        return isinstance(value, bool)
    if tname in _TRUE_TYPES:
        return isinstance(value, _TRUE_TYPES[tname])
    return True


def _resolve_ref(root, ref: str):
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported $ref (only local): {ref}")
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def _is_datetime(s: str) -> bool:
    try:
        v = s
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        datetime.fromisoformat(v)
        return True
    except Exception:
        return False


def validate(instance, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """返回错误列表（空 = 通过）。root 用于解析本地 $ref。"""
    if root is None:
        root = schema
    errors: list[str] = []

    if "$ref" in schema:
        target = _resolve_ref(root, schema["$ref"])
        # 2020-12 中 $ref 与其他关键字可共存，先校验 ref 再回落其余关键字
        errors.extend(validate(instance, target, root, path))

    if "type" in schema:
        t = schema["type"]
        types = t if isinstance(t, list) else [t]
        if not any(_type_ok(instance, x) for x in types):
            errors.append(f"{path}: 期望类型 {types}，实际 {type(instance).__name__}")
            return errors  # 类型不符，后续关键字无意义

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: 期望常量 {schema['const']!r}，实际 {instance!r}")

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} 不在枚举 {schema['enum']} 中")

    if isinstance(instance, str):
        pat = schema.get("pattern")
        if pat and re.search(pat, instance) is None:
            errors.append(f"{path}: 字符串 {instance!r} 不匹配 pattern {pat!r}")
        fmt = schema.get("format")
        if fmt == "date-time" and not _is_datetime(instance):
            errors.append(f"{path}: {instance!r} 不是合法 date-time")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} 小于 minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} 大于 maximum {schema['maximum']}")

    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: 缺少必填字段 {req!r}")
        props = schema.get("properties", {})
        for key, val in instance.items():
            if key in props:
                errors.extend(validate(val, props[key], root, f"{path}.{key}"))
            else:
                ap = schema.get("additionalProperties", True)
                if ap is False:
                    errors.append(f"{path}: 不允许的额外字段 {key!r}")
                elif isinstance(ap, dict):
                    errors.extend(validate(val, ap, root, f"{path}.{key}"))

    if isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, val in enumerate(instance):
                errors.extend(validate(val, items, root, f"{path}[{i}]"))
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: 数组长度 {len(instance)} 小于 minItems {schema['minItems']}")

    for kw in ("allOf", "anyOf", "oneOf"):
        if kw in schema:
            subs = schema[kw]
            if kw == "allOf":
                for sub in subs:
                    errors.extend(validate(instance, sub, root, path))
            elif kw == "anyOf":
                if not any(not validate(instance, sub, root, path) for sub in subs):
                    errors.append(f"{path}: 不满足 anyOf 任一分支")
            elif kw == "oneOf":
                passed = [sub for sub in subs if not validate(instance, sub, root, path)]
                if len(passed) != 1:
                    errors.append(f"{path}: oneOf 需恰好命中 1 个分支，实际 {len(passed)}")

    return errors
