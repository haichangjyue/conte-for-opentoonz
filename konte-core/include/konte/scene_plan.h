// SPDX-License-Identifier: BSD-3-Clause
// ScenePlan —— konte.json（决定稿）归一后的逐 cut 导出输入契约。
// 与 poc/konte_poc/scene_plan.py 输出保持一致；C++ 导出内核读取本结构生成 .tnz。
#pragma once
#ifndef KONTE_SCENE_PLAN_H
#define KONTE_SCENE_PLAN_H

#include <string>
#include <vector>

#include "konte/json.h"

namespace konte {

struct Rect { int x = 0, y = 0, w = 0, h = 0; };

struct Duration {
  std::string status;      // fixed | tbd | default
  int seconds = 0;
  int frames = 0;
  int totalFrames = 0;
  double durationSec = 0.0;
};

struct FrameInfo {
  std::string kind = "standard";  // standard | oversize
  Rect rect;
  Rect cameraBox;
};

struct DialogueLine { std::string character; std::string text; bool offscreen = false; };
struct MusicSe { std::string text; int atFrame = -1; bool hasAt = false; };

struct NoteColumns {
  std::string action;
  std::vector<DialogueLine> dialogue;
  std::vector<MusicSe> musicSe;
};

struct HoldFrames { int from = 1; int to = 0; };

struct ScenePlan {
  std::string cutId;
  std::string scene;
  std::string cut;
  int number = 0;
  int order = 0;
  std::string sceneFile;
  int fps = 24;
  Duration duration;
  std::string referenceImage;   // 相对导出目录（第一张参考图）
  std::vector<std::string> referenceImages;  // 多帧参考层：该 cut 的全部参考图（1..M 帧）
  std::string levelPath;        // 相对导出目录（参考层逻辑基名，如 scenes/X.ref.png）
  bool levelLock = true;
  HoldFrames hold;
  NoteColumns notes;
  FrameInfo frame;
  std::string cameraNote;
  bool hasSound = false;
  std::string soundPath;
  int soundOffsetFrames = 0;   // 声音起点相对该 cut 第 1 帧的偏移（>=0）
  std::string sequenceId;

  // 从 sceneplan JSON 解析；失败抛 JsonError/PlanError
  static ScenePlan fromJson(const Json& j);
};

class PlanError : public std::runtime_error {
public:
  explicit PlanError(const std::string& m) : std::runtime_error(m) {}
};

// 校验：fps>0、totalFrames 与秒帧一致、hold=1..N、文件名/参考图非空。
// 返回错误信息（空串=通过）。
std::string validatePlan(const ScenePlan& p);

}  // namespace konte

#endif  // KONTE_SCENE_PLAN_H
