# 导出内核输入契约（KERNEL CONTRACT）：ScenePlan → `.tnz`

> 本文是 Python PoC（`poc/konte_poc/scene_plan.py`）与 **OpenToonz C++ 导出内核**之间的接口契约。
> PoC 负责把 `konte.json`（决定稿）归一为逐 cut 的 **ScenePlan**；C++ 内核读取 ScenePlan，
> 调用 OT API 生成 `<SCENE>_<CUT>.tnz`。二者必须行为一致（同一份 `konte.json` → 等价交付物）。

## 1. ScenePlan 字段

见 `poc/examples/EP01/out/scenes/*.sceneplan.json`。关键字段：

| 字段 | 含义 | C++ 用法 |
|---|---|---|
| `sceneFile` | 目标 `.tnz` 文件名 | `scene.setScenePath(target/sceneFile)` |
| `fps` | 帧率（模板锁定，日式多 24） | `TProject::SceneProperties` / `initializeScene` |
| `duration.totalFrames` = N | 场景帧数（= 秒×fps+帧） | 参考层 hold 到第 N 帧 → `TXsheet` 帧数 = N |
| `referenceImage` / `referenceImages` / `level.path` | 渲染参考图（Raster）；`referenceImages` 为同一 cut 的 1..M 张画面（多帧参考层） | `scene.loadLevel(base.0001.png, fids=[1..M])` |
| `level.lock` | 参考层锁定不可编辑 | level 只读/锁 |
| `holdFrames {from:1,to:N}` | 参考层暴露区间 | `TXsheet::setCell` 第 1..N 帧；多帧时按画面数均匀分布 |
| `noteColumns.action/dialogue/musicSe` | 文字进 Note 列 | `TXsheet::getNotes()` 写文本轨 |
| `frame.kind` / `frame.rect` | `oversize`=超框(bleed) | 参考图按 rect 渲染（保留外溢），相机按模板 |
| `camera` / `sequenceId` / `sound` | 参考信息 | 相机参考层 / 目录分组 / 声音列 |

## 2. `.tnz` 生成算法（C++，对应《工程交接技术规格》§5.1 / 导出规格 A2）

```cpp
// 前置：project.status==final 且所有 cut.duration.status!=tbd（PoC 已强制）
for (auto& plan : loadScenePlans(dir)) {           // 按 order
    ToonzScene* scene = new ToonzScene();
    TProjectManager::initializeScene(scene);        // 套模板：相机尺寸、fps
    // 1) 参考层（Q8：渲染位图，锁定）
    TXshLevel* level = scene->loadLevel(plan.levelPath);   // Raster
    // 2) 时长钉定：hold 到第 N 帧
    int N = plan.totalFrames;
    TXsheet* xsheet = scene->getXsheet();
    int col = 0;
    for (int f = 1; f <= N; ++f) xsheet->setCell(f-1, col, level, /*cell*/0);
    xsheet->updateFrameCount();                     // -> 帧数 = N
    lockLevelReadOnly(level);                       // 参考层不可编辑
    // 3) 文字进 Note 列
    TXsheet::NoteSet notes = xsheet->getNotes();
    notes.setNote(col, "action",  plan.noteColumns.action);
    notes.setNote(col, "dialogue", join(plan.noteColumns.dialogue));
    notes.setNote(col, "musicSe", join(plan.noteColumns.musicSe));
    // 4) 声音（如有）：对齐帧时间
    if (plan.hasSound) attachSoundColumn(scene, plan.sound, plan.fps);
    // 5) 存盘（同名默认升版 + 保留旧版）
    scene->setScenePath(target / plan.sceneFile);
    scene->save();
}
writeManifest(...);   // 与 PoC manifest 结构一致
```

> 关键风险（须 P1 PoC 验证，见技术规格 §5.4/§8）：
> - `TXsheet` 帧数由内容最大帧决定 → 依赖"hold 到 N 帧"钉时长。
> - 声音切片与帧对齐、Note 列写入的确切 API。
> - ToonzScript 的 Scene 类**未暴露** `setFrameCount` → 帧数控制必须走 C++。

## 3. 一致性验收（对拍）

同一 `konte.json`：
1. PoC 产出：`manifest.json`（items/totalFrames/page）、`scenes/*.sceneplan.json`、`storyboard.pdf`。
2. C++ 内核产出：`<SCENE>_<CUT>.tnz`，打开后应满足：帧数 == `sceneplan.duration.totalFrames`；
   参考层显示正确并锁定；Note 含 action/台词/music-se；声音对齐。
3. CI 断言：两者 `manifest.items[]` 的 `cutId/sceneFile/totalFrames/durationSec/page` 完全一致。

## 4. 实现状态（P1 / C++ 导出内核）

- **已实现**（`konte-core/`）：零依赖 JSON、`ScenePlan` 解析与校验、导出编排、CLI `konte-export`、
  以及基于真实 OT 头文件签名的 `ot_scene_writer.cpp`（`KONTE_WITH_OPENTOONZ` 宏开关）。
- **已验证 · 纯逻辑**：C++ 内核编译通过、单测通过；`konte-export --dry-run` 读取 Python `poc`
  产出的 7 份 `*.sceneplan.json` 并输出计划 + 报告（跨语言对拍 OK）。
- **已验证 · 真实 .tnz（2026-11-12）**：在 Windows 上以 MSVC19.44 + Qt5.15.2(+QtScript) + OpenCV4.8 + Boost1.73
  构建 `KONTE_WITH_OPENTOONZ`，`konte-export` 生成 **7/7** `.tnz`，`loadFrameCount` 与
  `duration.totalFrames` 逐一相等（72/36/48/18/102/60/72）；`loadTnzFile` 重载校验
  `frameCount/notes/sounds` 全部通过（含 1 个带 WAV 的 cut：`sounds=1`）。
  **参考层锁定**：`TXshSimpleLevel::setIsReadOnly(true)` 且参考 PNG 置为只读（重载即只读）。环境与复现见
  `docs/BUILD_ENV_WINDOWS.md` / `scripts/build_export_with_ot.ps1`。
- **模板与打包（2026-11-12 收尾）**：`--template` 以模板 `.tnz` 为底，**保留模板全部图层（columns）**、仅清空模板 notes；
  模板层超长裁到 N、单帧静态层 hold 到 N；本 cut 参考层作为**新列**追加。实测模板相机 1280×720 生效、每 cut 输出两列（模板层+参考层）。
- **参考层命名（关键）**：参考图导出为 `<stem>.0001.png`，`.tnz` 内以 **`$scenefolder/<stem>.0001.png`** 记录。文件名**必须带帧号**：否则 OT 解析为 `NO_FRAME(-2)`，与单元格 `0001` 不匹配 → 空白层（Xsheet 有列但无画面）。
- **多帧参考层（一个工程多格画面）**：一个 cut 的多张画面写成**同一 level 的 1..M 帧**（源文件 `<stem>.ref.01.png...`，内核复制为 `<stem>.ref.0001.png...`），
  `loadLevel(base.0001.png, fids=[1..M])`；Xsheet 里按画面数均匀铺到该 cut 的 N 帧，可在 OT 中翻看。**仍是一个 cut 一个 `.tnz`**。
- **配置隔离（关键）**：导出进程启动时调用 `configureIsolatedEnv()`（内部 `TEnv::setArgPathValue` 覆盖 `TOONZPROFILES/CONFIG/PROJECTS/...` 到临时目录）。Windows 下 `TEnv` 只读注册表、不读环境变量；不隔离会改写用户 OpenToonz 的 `preferences.ini`（实测会把界面语言重置为 English）。
- **音频**：`cut.audio.path`（konte.schema 可选字段）经 ScenePlan 的 `sound.path` 传入；内核把 WAV 复制到场景目录并建立**单个连续 `ColumnLevel`（0..N-1）** 的 `TXshSoundColumn`。注意：若用多个重叠 `SoundCells`，OT 在关闭时可能因声音列定时器/播放器状态异常而崩溃（EXCEPTION_ACCESS_VIOLATION in `TSoundOutputDevice::isPlaying`）；因此必须保持单一完整音轨。**演示工程 EP01 已带音轨**（`audio/C001..C007.wav`）。
- **构建**：`pwsh -File scripts/build_kernel.ps1`（纯逻辑）；`pwsh -File scripts/build_export_with_ot.ps1`（真实 .tnz）。

