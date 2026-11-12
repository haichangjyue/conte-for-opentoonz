# SPDX-License-Identifier: BSD-3-Clause
"""konte_poc 命令行：validate / info / export。"""

from __future__ import annotations

import argparse
import json
import sys

from .errors import ExportGateError, InvariantError, SchemaError
from .export import export_project
from .batch import export_batch
from .package import build_package
from .model import KonteProject
from . import template as template_mod


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
            pdf_template=args.pdf_template,
            include_audio=not args.no_audio,
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


def _cmd_batch(args) -> int:
    try:
        report = export_batch(
            args.project, args.out,
            base_psd=args.base_psd, schema_path=args.schema,
            pdf_template=args.pdf_template, exporter=args.exporter,
            tnz_template=args.template, resume=not args.no_resume,
            include_audio=not args.no_audio, make_pdf=not args.no_pdf,
            force_pdf=args.force_pdf, pdf_split_pages=args.pdf_split_pages,
            quiet=args.quiet,
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


def _cmd_package(args) -> int:
    try:
        report = build_package(
            args.project, args.out_root,
            base_psd=args.base_psd, exporter=args.exporter,
            template=args.template, make_zip=not args.no_zip,
            schema_path=args.schema, pdf_template=args.pdf_template,
            include_audio=not args.no_audio, zip_name=args.zip_name,
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


def _cmd_templates(args) -> int:
    d = template_mod.TEMPLATE_DIR
    items = []
    for p in sorted(d.glob("*.json")):
        try:
            t = template_mod.load_template(p)
            items.append({
                "id": t.id, "name": t.name, "version": t.version,
                "file": str(p), "perPage": t.per_page,
                "canvas": list(t.canvas), "dpi": t.dpi,
                "basePsd": t.base_psd,
            })
        except Exception as e:  # noqa: BLE001
            items.append({"file": str(p), "error": str(e)})
    print(json.dumps(items, ensure_ascii=False, indent=2))
    return 0


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
    e.add_argument("--pdf-template", default=None,
                   help="PDF 版式模板 JSON（默认 konte-format/templates/scfilms_storyboard.json）")
    e.add_argument("--no-pdf", action="store_true", help="跳过 PDF 生成")
    e.add_argument("--no-audio", action="store_true", help="导出时剔除音频（ScenePlan.sound=null）")
    e.set_defaults(func=_cmd_export)

    p = sub.add_parser("package", help="交付打包：tnz + 参考图 + PDF + manifest + zip")
    p.add_argument("project")
    p.add_argument("--out-root", required=True, help="交付根目录（其下生成 <PROJECT>/ 与 <PROJECT>.zip）")
    p.add_argument("--base-psd", default=None)
    p.add_argument("--exporter", default=None, help="konte-export 可执行文件（生成真实 .tnz）")
    p.add_argument("--template", default=None, help="模板 .tnz")
    p.add_argument("--pdf-template", default=None, help="PDF 版式模板 JSON")
    p.add_argument("--no-zip", action="store_true")
    p.add_argument("--no-audio", action="store_true", help="打包剔除音频（.tnz 无声音列、不含 wav）")
    p.add_argument("--zip-name", default=None, help="zip 名称/版本（默认项目名）")
    p.set_defaults(func=_cmd_package)

    b = sub.add_parser("batch", help="批量导出（断点续 + 进度日志 + 失败汇总，支持 >200 cut）")
    b.add_argument("project")
    b.add_argument("--out", required=True, help="输出目录")
    b.add_argument("--base-psd", default=None)
    b.add_argument("--pdf-template", default=None)
    b.add_argument("--exporter", default=None, help="konte-export 可执行文件（生成真实 .tnz）")
    b.add_argument("--template", default=None, help="模板 .tnz")
    b.add_argument("--no-resume", action="store_true", help="禁用断点续（全部重算）")
    b.add_argument("--no-audio", action="store_true")
    b.add_argument("--no-pdf", action="store_true", help="跳过 PDF（>200 cut 推荐）")
    b.add_argument("--force-pdf", action="store_true", help="强制重建 PDF")
    b.add_argument("--pdf-split-pages", type=int, default=None,
                   help="分卷：每 N 页一个 PDF（storyboard.partNN.pdf）")
    b.add_argument("--quiet", action="store_true")
    b.set_defaults(func=_cmd_batch)

    t = sub.add_parser("templates", help="列出可用的 PDF 版式模板")
    t.set_defaults(func=_cmd_templates)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
