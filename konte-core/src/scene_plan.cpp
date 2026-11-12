// SPDX-License-Identifier: BSD-3-Clause
// ScenePlan JSON 解析与校验实现。
#include "konte/scene_plan.h"

#include <sstream>

namespace konte {

static int getInt(const Json& j, const char* k, int def) {
  return j.contains(k) ? (int)j.at(k).asInt() : def;
}
static std::string getStr(const Json& j, const char* k, const std::string& def = "") {
  return j.contains(k) && j.at(k).isString() ? j.at(k).asString() : def;
}

ScenePlan ScenePlan::fromJson(const Json& j) {
  if (!j.isObject()) throw PlanError("sceneplan 不是对象");
  ScenePlan p;
  p.cutId = getStr(j, "cutId");
  p.scene = getStr(j, "scene");
  p.cut = getStr(j, "cut");
  p.number = getInt(j, "number", 0);
  p.order = getInt(j, "order", 0);
  p.sceneFile = getStr(j, "sceneFile");
  p.fps = getInt(j, "fps", 24);

  if (j.contains("duration")) {
    const Json& d = j.at("duration");
    p.duration.status = getStr(d, "status", "fixed");
    p.duration.seconds = getInt(d, "seconds", 0);
    p.duration.frames = getInt(d, "frames", 0);
    p.duration.totalFrames = getInt(d, "totalFrames", 0);
    p.duration.durationSec = d.contains("durationSec") ? d.at("durationSec").asDouble() : 0.0;
  }
  p.referenceImage = getStr(j, "referenceImage");
  if (j.contains("referenceImages")) {
    const Json& arr = j.at("referenceImages");
    for (size_t i = 0; i < arr.size(); ++i)
      p.referenceImages.push_back(arr[i].asString());
  }
  if (p.referenceImages.empty() && !p.referenceImage.empty())
    p.referenceImages.push_back(p.referenceImage);
  if (j.contains("level")) {
    const Json& lv = j.at("level");
    p.levelPath = getStr(lv, "path", p.referenceImage);
    p.levelLock = lv.contains("lock") ? lv.at("lock").asBool() : true;
  }
  if (j.contains("holdFrames")) {
    const Json& h = j.at("holdFrames");
    p.hold.from = getInt(h, "from", 1);
    p.hold.to = getInt(h, "to", p.duration.totalFrames);
  } else {
    p.hold.from = 1;
    p.hold.to = p.duration.totalFrames;
  }
  if (j.contains("noteColumns")) {
    const Json& n = j.at("noteColumns");
    p.notes.action = getStr(n, "action");
    if (n.contains("dialogue")) {
      const Json& arr = n.at("dialogue");
      for (size_t i = 0; i < arr.size(); ++i) {
        const Json& dl = arr[i];
        DialogueLine line;
        line.character = getStr(dl, "character");
        line.text = getStr(dl, "text");
        line.offscreen = dl.contains("offscreen") ? dl.at("offscreen").asBool() : false;
        p.notes.dialogue.push_back(line);
      }
    }
    if (n.contains("musicSe")) {
      const Json& arr = n.at("musicSe");
      for (size_t i = 0; i < arr.size(); ++i) {
        const Json& m = arr[i];
        MusicSe ms;
        ms.text = getStr(m, "text");
        if (m.contains("atFrame")) { ms.atFrame = (int)m.at("atFrame").asInt(); ms.hasAt = true; }
        p.notes.musicSe.push_back(ms);
      }
    }
  }
  if (j.contains("frame")) {
    const Json& f = j.at("frame");
    p.frame.kind = getStr(f, "kind", "standard");
    auto readRect = [](const Json& r, Rect& out) {
      if (!r.isObject()) return;
      out.x = getInt(r, "x", 0); out.y = getInt(r, "y", 0);
      out.w = getInt(r, "w", 0); out.h = getInt(r, "h", 0);
    };
    if (f.contains("rect")) readRect(f.at("rect"), p.frame.rect);
    if (f.contains("cameraBox")) readRect(f.at("cameraBox"), p.frame.cameraBox);
  }
  if (j.contains("camera")) p.cameraNote = getStr(j.at("camera"), "note");
  p.sequenceId = getStr(j, "sequenceId");
  if (j.contains("sound") && !j.at("sound").isNull()) {
    p.hasSound = true;
    p.soundPath = getStr(j.at("sound"), "path");
    p.soundOffsetFrames = getInt(j.at("sound"), "offsetFrames", 0);
  }
  return p;
}

std::string validatePlan(const ScenePlan& p) {
  std::ostringstream e;
  if (p.sceneFile.empty()) e << "sceneFile 为空; ";
  if (p.fps <= 0) e << "fps 非法; ";
  if (p.duration.totalFrames <= 0) e << "totalFrames<=0; ";
  if (p.duration.status == "fixed") {
    int expect = p.duration.seconds * p.fps + p.duration.frames;
    if (expect != p.duration.totalFrames)
      e << "时长不一致: totalFrames=" << p.duration.totalFrames << " 期望 " << expect << "; ";
  }
  if (p.hold.from != 1 || p.hold.to != p.duration.totalFrames)
    e << "holdFrames 应为 1..N; ";
  if (p.referenceImage.empty()) e << "referenceImage 为空; ";
  if (p.frame.kind != "standard" && p.frame.kind != "oversize")
    e << "frame.kind 非法(" << p.frame.kind << "); ";
  if (p.hasSound && p.soundOffsetFrames < 0)
    e << "sound.offsetFrames 不能为负(" << p.soundOffsetFrames << "); ";
  return e.str();
}

}  // namespace konte
