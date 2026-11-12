# SPDX-License-Identifier: BSD-3-Clause
"""konte_poc 命令行：validate / info / export。"""

from __future__ import annotations

import argparse
import json
import sys

from .errors import ExportGateError, InvariantError, SchemaError
from .export import export_project
from .package import build_package
from .model import KonteProject


def _cmd_validate(args) -> int:
    try:
        p = KonteProject.load(args.project, schema_path=args.schema)
    except (SchemaError, InvariantError) as e:
        print(f"[INVALID] {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(f"[OK] konte.json 通过 schema + 不变量校验：{len(p.data['cuts'])} cuts, "
          f"status={p.status}, fps={p.fps}")
    return 0


def _cmd_info(args) -> int:
    p = KonteProject.load(args.project, schema_path=args.schema)
    print(json.dumps({
        "title": p.project.get("title"),
        "status": p.status,
        "fps": p.fps,
        "frame": p.project.get("frame"),
        "cuts": len(p.data["cuts"]),
        "sequences": p.data.get("sequences", []),
    }, ensure_ascii=False, indent=2))
    return 0


def _cmd_export(args) -> int:
    try:
        report = export_project(
            args.project, args.out,
            base_psd=args.base_psd, schema_path=args.schema,
            targets={"pdf": not args.no_pdf, "scenes": True, "package": True},
        )
    except ExportGateError as e:
        print(f"[GATE] {e}", file=sys.stderr)
        for d in e.details:
            print(f"  - {d}", file=sys.stderr)
        return 3
    except (SchemaError, InvariantError) as e:
        print(f"[INVALID] {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _cmd_package(args) -> int:
    try:
        report = build_package(
            args.project, args.out_root,
            base_psd=args.base_psd, exporter=args.exporter,
            template=args.template, make_zip=not args.no_zip,
            schema_path=args.schema,
        )
    except ExportGateError as e:
        print(f"[GATE] {e}", file=sys.stderr)
        for d in e.details:
            print(f"  - {d}", file=sys.stderr)
        return 3
    except (SchemaError, InvariantError) as e:
        print(f"[INVALID] {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="konte-poc", description="konte-core PoC 工具（导出/校验）")
    ap.add_argument("--schema", default=None, help="konte.schema.json 路径（默认用仓库内 konte-format）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="校验 konte.json（schema + 不变量）")
    v.add_argument("project")
    v.set_defaults(func=_cmd_validate)

    i = sub.add_parser("info", help="打印项目摘要")
    i.add_argument("project")
    i.set_defaults(func=_cmd_info)

    e = sub.add_parser("export", help="导出（决定稿）：参考图 + ScenePlan + A4 PDF + manifest")
    e.add_argument("project")
    e.add_argument("--out", required=True, help="输出目录")
    e.add_argument("--base-psd", default=None, help="空白底版 PSD（默认用内置兜底网格）")
    e.add_argument("--no-pdf", action="store_true", help="跳过 PDF 生成")
    e.set_defaults(func=_cmd_export)

    p = sub.add_parser("package", help="交付打包：tnz + 参考图 + PDF + manifest + zip")
    p.add_argument("project")
    p.add_argument("--out-root", required=True, help="交付根目录（其下生成 <PROJECT>/ 与 <PROJECT>.zip）")
    p.add_argument("--base-psd", default=None)
    p.add_argument("--exporter", default=None, help="konte-export 可执行文件（生成真实 .tnz）")
    p.add_argument("--template", default=None, help="模板 .tnz")
    p.add_argument("--no-zip", action="store_true")
    p.set_defaults(func=_cmd_package)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
