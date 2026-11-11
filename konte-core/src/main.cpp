// SPDX-License-Identifier: BSD-3-Clause
// konte-export：读 scenes/*.sceneplan.json → 导出 .tnz（OT）或 dry-run 计划。
//
// 用法：
//   konte-export --sceneplans DIR --out DIR [--dry-run] [--template X.tnz] [--overwrite]
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "konte/export_kernel.h"
#include "konte/json.h"
#include "konte/scene_plan.h"

namespace fs = std::filesystem;
using namespace konte;

static std::string readFile(const fs::path& p) {
  std::ifstream f(p, std::ios::binary);
  std::ostringstream ss;
  ss << f.rdbuf();
  return ss.str();
}

int main(int argc, char** argv) {
  std::string sceneDir, outDir, templatePath;
  bool dryRun = false, overwrite = false;

  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    auto next = [&](const char* name) -> std::string {
      if (i + 1 >= argc) { std::cerr << "missing value for " << name << "\n"; std::exit(2); }
      return argv[++i];
    };
    if (a == "--sceneplans") sceneDir = next("--sceneplans");
    else if (a == "--out") outDir = next("--out");
    else if (a == "--template") templatePath = next("--template");
    else if (a == "--dry-run") dryRun = true;
    else if (a == "--overwrite") overwrite = true;
    else if (a == "-h" || a == "--help") {
      std::cout << "konte-export --sceneplans DIR --out DIR [--dry-run] [--template X.tnz] [--overwrite]\n";
      return 0;
    } else { std::cerr << "unknown arg: " << a << "\n"; return 2; }
  }
  if (sceneDir.empty() || outDir.empty()) {
    std::cerr << "usage: konte-export --sceneplans DIR --out DIR [--dry-run] [--template X.tnz]\n";
    return 2;
  }

  std::vector<ScenePlan> plans;
  int parseErrors = 0;
  if (!fs::exists(sceneDir)) { std::cerr << "sceneplans dir not found: " << sceneDir << "\n"; return 2; }

  std::vector<fs::path> files;
  for (auto& e : fs::directory_iterator(sceneDir)) {
    if (!e.is_regular_file()) continue;
    std::string name = e.path().filename().string();
    const std::string suffix = ".sceneplan.json";
    if (name.size() >= suffix.size() && name.compare(name.size() - suffix.size(), suffix.size(), suffix) == 0)
      files.push_back(e.path());
  }
  std::sort(files.begin(), files.end());

  for (auto& f : files) {
    try {
      Json j = Json::parse(readFile(f));
      plans.push_back(ScenePlan::fromJson(j));
    } catch (const std::exception& ex) {
      ++parseErrors;
      std::cerr << "[PARSE-ERR] " << f.string() << ": " << ex.what() << "\n";
    }
  }

  std::cout << "sceneplans: " << plans.size() << " loaded, parseErrors=" << parseErrors
            << ", openToonz=" << (openToonzAvailable() ? "yes" : "no")
            << ", dryRun=" << (dryRun ? "yes" : "no") << "\n";

  ExportOptions opt;
  opt.outDir = outDir;
  opt.templatePath = templatePath;
  opt.dryRun = dryRun;
  opt.overwrite = overwrite;

  ExportKernel kernel;
  ExportResult res = kernel.run(plans, opt);

  for (auto& s : res.scenes) {
    if (s.ok) std::cout << "  [OK]   " << s.sceneFile << "  (" << s.totalFrames << "f) -> " << s.artifact << "\n";
    else      std::cout << "  [FAIL] " << s.sceneFile << "  : " << s.error << "\n";
  }
  std::cout << "done. ok=" << res.okCount << " fail=" << res.failCount
            << " report=" << res.reportPath << "\n";
  return (res.failCount == 0 && parseErrors == 0) ? 0 : 1;
}
