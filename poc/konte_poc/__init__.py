# SPDX-License-Identifier: BSD-3-Clause
"""konte_poc —— konte-core 的 Python 参考实现 / PoC 验证器。

用途（对应《工程交接技术规格》§8 PoC）：
- P4：把 konte.json（决定稿）+ PSD 底版 + 实测坐标 → A4·5-cut 分镜 PDF（叠图法）。
- 校验：konte.json 通过 `konte.schema.json`（2020-12 子集）+ 核心不变量。
- 导出计划：为每个 cut 产出 ScenePlan（.tnz 生成内核的输入契约）+ 参考图 + manifest。

注意：真正的 `.tnz` 由 OpenToonz C++ 导出内核生成（见 KERNEL_CONTRACT.md）。
本包只做"能在此环境独立跑通、可验证"的格式/排版/PDF/计划部分，作为 C++ 内核的对拍基准。
"""

__version__ = "0.1.0"
