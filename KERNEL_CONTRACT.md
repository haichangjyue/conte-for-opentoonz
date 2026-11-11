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
| `referenceImage` / `level.path` | 渲染参考图（Raster） | `scene.loadLevel(refPng)` |
| `level.lock` | 参考层锁定不可编辑 | level 只读/锁 |
| `holdFrames {from:1,to:N}` | 参考层暴露区间 | `TXsheet::setCell` / `exposeLevel` 第 1..N 帧 |
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
