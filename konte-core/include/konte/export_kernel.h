// SPDX-License-Identifier: BSD-3-Clause
// konte-core 导出内核：ScenePlan[] → .tnz（OT 可用时）或 dry-run 计划（无 OT 时）。
#pragma once
#ifndef KONTE_EXPORT_KERNEL_H
#define KONTE_EXPORT_KERNEL_H

#include <string>
#include <vector>

#include "konte/scene_plan.h"

namespace konte {

struct ExportOptions {
  std::string outDir;        // 产物根目录
  std::string templatePath;  // 模板 .tnz（可选）
  bool dryRun = false;       // true: 不调用 OT，仅校验并写 .plan.txt
  bool overwrite = false;    // 同名是否覆盖（默认升版 _v2）
};

struct SceneResult {
  std::string cutId;
  std::string sceneFile;
  int totalFrames = 0;
  bool ok = false;
  std::string artifact;   // 生成的文件路径（.tnz 或 .plan.txt）
  std::string error;
};

struct ExportResult {
  std::vector<SceneResult> scenes;
  int okCount = 0;
  int failCount = 0;
  bool wroteReport = false;
  std::string reportPath;
};

class ExportKernel {
public:
  // 依据 ScenePlan 列表导出。逐个 cut 独立处理，一个失败不影响其余。
  ExportResult run(const std::vector<ScenePlan>& plans, const ExportOptions& opt) const;
};

// 是否在编译期接入了 OpenToonz（KONTE_WITH_OPENTOONZ）。
bool openToonzAvailable();

// 用 OpenToonz 生成单个 .tnz。未接入 OT 时返回 false 并写 err。
bool writeSceneWithOpenToonz(const ScenePlan& plan, const std::string& outFile,
                             const std::string& templatePath, std::string& err);

}  // namespace konte

#endif  // KONTE_EXPORT_KERNEL_H
