// SPDX-License-Identifier: BSD-3-Clause
// konte-core 纯逻辑单元测试（零依赖，clang++/g++ 可直接编译运行）。
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

#include "konte/export_kernel.h"
#include "konte/json.h"
#include "konte/scene_plan.h"

namespace fs = std::filesystem;
using namespace konte;

static const char* kSamplePlan = R"JSON({
  "cutId": "ep01-c001",
  "scene": "EP01",
  "cut": "C001",
  "number": 1,
  "order": 1,
  "sceneFile": "EP01_C001.tnz",
  "fps": 24,
  "duration": { "status": "fixed", "seconds": 3, "frames": 0, "totalFrames": 72, "durationSec": 3.0 },
  "referenceImage": "scenes/EP01_C001.ref.png",
  "level": { "type": "raster", "path": "scenes/EP01_C001.ref.png", "lock": true },
  "holdFrames": { "from": 1, "to": 72 },
  "noteColumns": {
    "action": "城市远景。カメラ固定。",
    "dialogue": [ { "character": "AKIRA", "text": "行くぞ。", "offscreen": false } ],
    "musicSe": [ { "text": "SE: 足音", "atFrame": 0 } ]
  },
  "frame": { "kind": "standard", "rect": {"x":0,"y":0,"w":1920,"h":1080},
             "cameraBox": {"x":0,"y":0,"w":1920,"h":1080} },
  "camera": { "note": "固定", "keyframes": [] },
  "sound": null,
  "sequenceId": "seq1"
})JSON";

static int g_fail = 0;
#define CHECK(cond, msg) do { if(!(cond)){ std::cerr << "FAIL: " << msg << "\n"; ++g_fail; } } while(0)

static void testParse() {
  Json j = Json::parse(kSamplePlan);
  ScenePlan p = ScenePlan::fromJson(j);
  CHECK(p.cutId == "ep01-c001", "cutId");
  CHECK(p.sceneFile == "EP01_C001.tnz", "sceneFile");
  CHECK(p.fps == 24, "fps");
  CHECK(p.duration.totalFrames == 72, "totalFrames");
  CHECK(p.hold.from == 1 && p.hold.to == 72, "hold");
  CHECK(p.levelLock, "levelLock");
  CHECK(p.notes.dialogue.size() == 1, "dialogue size");
  CHECK(p.notes.dialogue[0].character == "AKIRA", "dialogue char utf8");
  CHECK(p.notes.musicSe.size() == 1 && p.notes.musicSe[0].hasAt, "musicSe");
  CHECK(validatePlan(p).empty(), "sample should validate");
}

static void testValidate() {
  Json j = Json::parse(kSamplePlan);
  ScenePlan p = ScenePlan::fromJson(j);
  p.duration.totalFrames = 71;                 // 破坏秒帧一致
  CHECK(!validatePlan(p).empty(), "bad arithmetic must fail");
  ScenePlan q = ScenePlan::fromJson(Json::parse(kSamplePlan));
  q.hold.to = 10;
  CHECK(!validatePlan(q).empty(), "bad hold must fail");
}

static void testJsonRoundtrip() {
  Json j = Json::parse(kSamplePlan);
  std::string dumped = j.dump(0);
  Json j2 = Json::parse(dumped);
  CHECK(j2.at("cutId").asString() == "ep01-c001", "roundtrip cutId");
  CHECK(j2.at("noteColumns").at("action").asString().find("城市") != std::string::npos, "utf8 roundtrip");
}

static void testKernelDryRun() {
  Json j = Json::parse(kSamplePlan);
  std::vector<ScenePlan> plans{ScenePlan::fromJson(j)};
  fs::path out = fs::temp_directory_path() / "konte_cpp_test_out";
  fs::remove_all(out);
  ExportOptions opt; opt.outDir = out.string(); opt.dryRun = true;
  ExportKernel k;
  ExportResult r = k.run(plans, opt);
  CHECK(r.okCount == 1 && r.failCount == 0, "dry-run ok count");
  CHECK(fs::exists(out / "EP01_C001.tnz.plan.txt"), "plan.txt written");
  CHECK(fs::exists(out / "export_report.json"), "report written");
  fs::remove_all(out);
}

static void testSoundOffset() {
  std::string s(kSamplePlan);
  auto pos = s.find("\"sound\": null");
  CHECK(pos != std::string::npos, "sample has sound field");
  s.replace(pos, 13, "\"sound\": {\"path\": \"audio/C001.wav\", \"offsetFrames\": 12}");
  ScenePlan p = ScenePlan::fromJson(Json::parse(s));
  CHECK(p.hasSound, "hasSound");
  CHECK(p.soundPath == "audio/C001.wav", "soundPath");
  CHECK(p.soundOffsetFrames == 12, "sound offset parsed");
  CHECK(validatePlan(p).empty(), "offset plan validates");
  ScenePlan q = ScenePlan::fromJson(Json::parse(s));
  q.soundOffsetFrames = -1;
  CHECK(!validatePlan(q).empty(), "negative offset must fail");
}

static void testReferenceImages() {
  std::string s(kSamplePlan);
  auto pos = s.find("\"referenceImage\": \"scenes/EP01_C001.ref.png\",");
  CHECK(pos != std::string::npos, "referenceImage line");
  std::string ins = "\"referenceImages\": [\"scenes/r1.png\", \"scenes/r2.png\"],";
  s.insert(pos, ins + "\n  ");
  ScenePlan p = ScenePlan::fromJson(Json::parse(s));
  CHECK(p.referenceImages.size() == 2, "multi referenceImages parsed");
  CHECK(p.referenceImages[0] == "scenes/r1.png", "referenceImages[0]");
  // 无 referenceImages 时回退为单张 referenceImage
  ScenePlan q = ScenePlan::fromJson(Json::parse(kSamplePlan));
  CHECK(q.referenceImages.size() == 1, "fallback one reference");
}

int main() {
  testParse();
  testValidate();
  testJsonRoundtrip();
  testSoundOffset();
  testReferenceImages();
  testKernelDryRun();
  if (g_fail == 0) { std::cout << "ALL C++ TESTS PASSED\n"; return 0; }
  std::cerr << g_fail << " checks failed\n";
  return 1;
}
