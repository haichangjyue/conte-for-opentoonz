// SPDX-License-Identifier: BSD-3-Clause
// 导出内核编排：校验 → 逐 cut 生成（OT 或 dry-run）→ 汇总报告。
#include "konte/export_kernel.h"

#include <filesystem>
#include <fstream>
#include <sstream>

namespace fs = std::filesystem;

namespace konte {

static std::string makeUniquePath(const fs::path& desired, bool overwrite) {
  if (overwrite || !fs::exists(desired)) return desired.string();
  fs::path dir = desired.parent_path();
  std::string stem = desired.stem().string();
  std::string ext = desired.extension().string();
  for (int v = 2; v < 10000; ++v) {
    fs::path cand = dir / (stem + "_v" + std::to_string(v) + ext);
    if (!fs::exists(cand)) return cand.string();
  }
  return desired.string();
}

static std::string planText(const ScenePlan& p) {
  std::ostringstream o;
  o << "# konte-core dry-run plan\n";
  o << "cutId=" << p.cutId << "\n";
  o << "scene=" << p.scene << " cut=" << p.cut << " order=" << p.order << "\n";
  o << "sceneFile=" << p.sceneFile << "\n";
  o << "fps=" << p.fps << " totalFrames=" << p.duration.totalFrames
    << " (" << p.duration.seconds << "+" << p.duration.frames << " @ " << p.fps << "fps)\n";
  o << "holdFrames=" << p.hold.from << ".." << p.hold.to << "\n";
  o << "level=" << p.levelPath << " lock=" << (p.levelLock ? "true" : "false") << "\n";
  o << "referenceImage=" << p.referenceImage << "\n";
  o << "frame.kind=" << p.frame.kind << " rect=" << p.frame.rect.x << "," << p.frame.rect.y
    << "," << p.frame.rect.w << "," << p.frame.rect.h << "\n";
  o << "action=" << p.notes.action << "\n";
  for (auto& d : p.notes.dialogue) o << "dialogue[" << d.character << "]=" << d.text << "\n";
  for (auto& m : p.notes.musicSe) o << "musicSe=" << m.text << "\n";
  return o.str();
}

ExportResult ExportKernel::run(const std::vector<ScenePlan>& plans, const ExportOptions& opt) const {
  ExportResult res;
  std::error_code ec;
  fs::create_directories(opt.outDir, ec);

  for (const auto& p : plans) {
    SceneResult r;
    r.cutId = p.cutId;
    r.sceneFile = p.sceneFile;
    r.totalFrames = p.duration.totalFrames;

    std::string verr = validatePlan(p);
    if (!verr.empty()) {
      r.ok = false;
      r.error = verr;
      res.scenes.push_back(r);
      continue;
    }

    fs::path desired = fs::path(opt.outDir) / p.sceneFile;
    std::string outFile = makeUniquePath(desired, opt.overwrite);

    if (opt.dryRun) {
      std::string planFile = outFile + ".plan.txt";
      std::ofstream f(planFile, std::ios::binary);
      f << planText(p);
      f.close();
      r.ok = true;
      r.artifact = planFile;
    } else if (!openToonzAvailable()) {
      r.ok = false;
      r.error = "本内核未以 KONTE_WITH_OPENTOONZ 构建，无法生成 .tnz（可用 --dry-run 验证计划）";
    } else {
      std::string err;
      if (writeSceneWithOpenToonz(p, outFile, opt.templatePath, err)) {
        r.ok = true;
        r.artifact = outFile;
      } else {
        r.ok = false;
        r.error = err.empty() ? "writeScene 失败" : err;
      }
    }
    res.scenes.push_back(r);
  }

  for (auto& s : res.scenes) (s.ok ? res.okCount : res.failCount)++;

  // 报告
  Json report = Json::object();
  report["okCount"] = Json::integer(res.okCount);
  report["failCount"] = Json::integer(res.failCount);
  report["dryRun"] = Json(opt.dryRun);
  report["openToonz"] = Json(openToonzAvailable());
  Json arr = Json::array();
  for (auto& s : res.scenes) {
    Json o = Json::object();
    o["cutId"] = Json(s.cutId);
    o["sceneFile"] = Json(s.sceneFile);
    o["totalFrames"] = Json::integer(s.totalFrames);
    o["ok"] = Json(s.ok);
    o["artifact"] = Json(s.artifact);
    o["error"] = Json(s.error);
    arr.push_back(o);
  }
  report["scenes"] = arr;
  fs::path rep = fs::path(opt.outDir) / "export_report.json";
  std::ofstream rf(rep.string(), std::ios::binary);
  rf << report.dump(2) << "\n";
  rf.close();
  res.wroteReport = true;
  res.reportPath = rep.string();
  return res;
}

}  // namespace konte
