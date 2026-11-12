# SPDX-License-Identifier: BSD-3-Clause
"""交付打包：把 Python 侧（参考图/PDF/manifest/ScenePlan）与 C++ 侧（.tnz）汇成一个可交付目录。

产物结构（对应《工程交接技术规格》§5.3）：
  <out_root>/<PROJECT>/
    scenes/<SCENE>_<CUT>.tnz
    scenes/<SCENE>_<CUT>.ref.png      # 与 .tnz 同目录，供相对 $scenefolder 引用
    references/<SCENE>_<CUT>.png      # 给原画的成形参考图
    storyboard.pdf
    manifest.json
    DELIVERY.md
  <out_root>/<PROJECT>.zip            # 整包压缩（可选）

若提供 konte-export 可执行文件，会调用它把 ScenePlan 生成真实 .tnz；否则只做无 .tnz 的结构包（并标注）。
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from . import minischema
from .export import export_project
from .model import KonteProject

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _audio_source(project: KonteProject, cut: dict):
    audio = cut.get("audio")
    if not audio or not audio.get("path"):
        return None
    p = Path(audio["path"])
    return p if p.is_absolute() else (project.base_dir / p)


def _exporter_env(exporter: str | Path) -> dict:
    """为 konte-export 子进程构造环境：DLL 搜索路径 + 隔离的 TOONZ 配置目录。

    隔离可避免导出进程改写用户 OpenToonz 的 preferences.ini（含界面语言）。
    """
    env = os.environ.copy()
    repo = _REPO_ROOT
    parts = [str(Path(exporter).parent)]
    candidates = [
        os.environ.get("KONTE_QT_BIN"),
        os.environ.get("KONTE_OPENCV_BIN"),
        r"X:\agent\tools\Qt\5.15.2\msvc2019_64\bin",
        r"X:\agent\tools\opencv\opencv\build\x64\vc16\bin",
        str(repo / "toonz" / "thirdparty" / "libmypaint" / "dist" / "64"),
        str(repo / "toonz" / "thirdparty" / "glew" / "glew-1.9.0" / "bin" / "64bit"),
        str(repo / "toonz" / "thirdparty" / "glut" / "3.7.6" / "lib"),
        r"C:\Windows\System32",
        r"C:\Windows",
    ]
    for c in candidates:
        if c and Path(c).exists():
            parts.append(c)
    env["PATH"] = os.pathsep.join(parts + [env.get("PATH", "")])

    iso = Path(tempfile.gettempdir()) / "konte_ot_env"
    mapping = {
        "TOONZPROFILES": "profiles", "TOONZCONFIG": "config", "TOONZPROJECTS": "projects",
        "TOONZLIBRARY": "library", "TOONZSTUDIOPALETTE": "studopalette", "TOONZFXPRESETS": "fxs",
    }
    for k, sub in mapping.items():
        d = iso / sub
        d.mkdir(parents=True, exist_ok=True)
        env[k] = str(d)
    env["TOONZROOT"] = str(repo / "toonz" / "stuff")
    return env


def _clean(d: Path):
    if not d.exists():
        return
    # 先解除只读（导出内核会把参考图置只读），否则 Windows 下 rmtree 会失败
    for root, dirs, files in os.walk(d):
        for name in files:
            try:
                os.chmod(os.path.join(root, name), stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
        for name in dirs:
            try:
                os.chmod(os.path.join(root, name), stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
    try:
        os.chmod(d, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass
    shutil.rmtree(d)


def build_package(
    project_path: str | Path,
    out_root: str | Path,
    *,
    base_psd: str | Path | None = None,
    exporter: str | Path | None = None,
    template: str | Path | None = None,
    make_zip: bool = True,
    schema_path: str | Path | None = None,
    pdf_template=None,
    include_audio: bool = True,
    zip_name: str | None = None,
) -> dict:
    project = KonteProject.load(project_path, schema_path=schema_path)
    project.check_export_gate()
    title = project.data["project"].get("title", "project")

    root = Path(out_root)
    pkg = root / title
    build = root / ("_build_" + title)
    _clean(pkg)
    _clean(build)

    # 1) Python 侧：参考图 + ScenePlan + PDF + 中间 manifest
    py_report = export_project(project_path, build, base_psd=base_psd,
                               schema_path=schema_path,
                               targets={"pdf": True, "scenes": True, "package": False},
                               pdf_template=pdf_template, include_audio=include_audio)
    (pkg / "scenes").mkdir(parents=True, exist_ok=True)
    (pkg / "references").mkdir(parents=True, exist_ok=True)

    # 2) C++ 侧：ScenePlan → .tnz（若提供 exporter）
    tnz_files: list[str] = []
    tnz_error = None
    if exporter and Path(exporter).exists():
        cmd = [str(exporter), "--sceneplans", str(build / "scenes"), "--out", str(pkg / "scenes")]
        if template:
            cmd += ["--template", str(template)]
        env = _exporter_env(exporter)
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            tnz_error = (f"exit {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        tnz_files = sorted(p.name for p in (pkg / "scenes").glob("*.tnz"))
        # 清理 C++ 导出内核的构建产物，保持交付目录干净
        for junk in ("export_report.json",):
            jp = pkg / "scenes" / junk
            if jp.exists():
                jp.unlink()
        icons = pkg / "scenes" / "sceneIcons"
        if icons.exists():
            shutil.rmtree(icons, ignore_errors=True)
    else:
        tnz_error = "未提供 konte-export（跳过 .tnz 生成）"

    # 3) 参考图 + PDF 入包
    for p in (build / "references").glob("*.png"):
        shutil.copyfile(p, pkg / "references" / p.name)
    if (build / "storyboard.pdf").exists():
        shutil.copyfile(build / "storyboard.pdf", pkg / "storyboard.pdf")

    # 3b) 音频入包（若含音频；导出内核通常会复制 wav，非 exporter 路径在此补齐）
    audio_count = 0
    if include_audio:
        for cut in project.sorted_cuts():
            src = _audio_source(project, cut)
            if not src or not Path(src).exists():
                continue
            dst = pkg / "scenes" / Path(src).name
            if not dst.exists():
                shutil.copyfile(src, dst)
            audio_count += 1

    # 4) manifest（按交付目录布局）
    man = json.loads((build / "manifest.json").read_text(encoding="utf-8"))
    man["packageDir"] = str(pkg)
    man["pdf"] = "storyboard.pdf" if (pkg / "storyboard.pdf").exists() else None
    man["includeAudio"] = bool(include_audio)
    (pkg / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5) DELIVERY.md
    (pkg / "DELIVERY.md").write_text(_delivery_md(project, man, tnz_files, tnz_error), encoding="utf-8")

    # 6) 校验
    verify = _verify_package(pkg, man, expect_tnz=bool(tnz_files), include_audio=include_audio)
    report = {
        "project": title,
        "packageDir": str(pkg),
        "cutCount": py_report["cutCount"],
        "pageCount": py_report["pageCount"],
        "tnzCount": len(tnz_files),
        "tnzError": tnz_error,
        "verify": verify,
        "pdf": py_report["pdf"],
        "pdfTemplate": py_report.get("pdfTemplate"),
        "includeAudio": bool(include_audio),
        "audioCount": audio_count if include_audio else 0,
    }

    # 7) zip（可选自定义命名/版本）
    if make_zip:
        zname = (zip_name or title).strip()
        if zname.lower().endswith(".zip"):
            zname = zname[:-4]
        zip_base = root / zname
        zip_path = shutil.make_archive(str(zip_base), "zip", root_dir=str(pkg.parent), base_dir=pkg.name)
        report["zip"] = zip_path
        report["zipName"] = zname + ".zip"

    # 清理中间构建目录
    _clean(build)
    report["ok"] = verify["ok"] and (len(tnz_files) > 0)
    (pkg / "package_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _verify_package(pkg: Path, man: dict, *, expect_tnz: bool, include_audio: bool = True) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    items = man.get("items", [])
    for it in items:
        sf = pkg / it["sceneFile"]
        if sf.exists():
            pass
        elif expect_tnz:
            errors.append(f"缺少场景文件: {it['sceneFile']}")
        else:
            warnings.append(f"未生成 .tnz: {it['sceneFile']}")
        ri = it.get("referenceImage")
        if ri and not (pkg / ri).exists():
            errors.append(f"缺少参考图: {ri}")
        af = it.get("audioFile")
        if include_audio and it.get("hasAudio") and af:
            if not (pkg / af).exists():
                errors.append(f"缺少音频: {af}")
    if not (pkg / "storyboard.pdf").exists():
        errors.append("缺少 storyboard.pdf")
    # manifest schema
    schema_file = _REPO_ROOT / "konte-format" / "manifest.schema.json"
    if schema_file.exists():
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        serr = minischema.validate(man, schema)
        errors.extend(f"manifest.schema: {e}" for e in serr)
    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def _delivery_md(project: KonteProject, man: dict, tnz_files: list[str], tnz_error) -> str:
    fps = project.fps
    cuts = len(man.get("items", []))
    lines = [
        f"# 交付说明 · {man.get('projectId')}",
        "",
        f"- 帧率：{fps} fps",
        f"- cut 数：{cuts}",
        f"- 分镜 PDF：storyboard.pdf（A4·5-cut）",
        f"- 工程：scenes/*.tnz（{len(tnz_files)} 个）＋ 同名 .ref.png（参考层）",
        f"- 参考图：references/*.png",
        "",
        "## 结构",
        "```",
        f"{man.get('projectId')}/",
        "├─ scenes/        # *.tnz + *.ref.png（相对 $scenefolder 引用）",
        "├─ references/    # 成形参考图（给原画）",
        "├─ storyboard.pdf # A4·5-cut 分镜",
        "├─ manifest.json  # 产物清单",
        "└─ DELIVERY.md",
        "```",
        "",
        "## 备注",
        "- 参考层（.ref.png）已置只读并锁定；`.tnz` 内以相对路径引用。",
        "- 本包由 konte-core 导出内核生成；决定稿闸门：仅 final 且无 TBD 时长可导出。",
    ]
    if tnz_error:
        lines += ["", f"> ⚠ .tnz 生成提示：{tnz_error}"]
    return "\n".join(lines) + "\n"
