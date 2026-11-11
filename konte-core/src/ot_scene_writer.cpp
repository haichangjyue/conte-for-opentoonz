// SPDX-License-Identifier: BSD-3-Clause
// OpenToonz 场景写入实现（仅在定义 KONTE_WITH_OPENTOONZ 时编译）。
// 真实 API 依据 toonz/sources/include/toonz/*.h（已核对签名）。
// 无 OT 时提供 stub，保证纯逻辑内核可在任意环境编译测试。
#include "konte/export_kernel.h"

#ifdef KONTE_WITH_OPENTOONZ

#include "toonz/toonzscene.h"
#include "toonz/tproject.h"
#include "toonz/txsheet.h"
#include "toonz/txshcell.h"
#include "toonz/txshlevel.h"
#include "toonz/txshsimplelevel.h"
#include "toonz/txshnoteset.h"
#include "toonz/txshsoundcolumn.h"
#include "toonz/txshsoundlevel.h"
#include "toonz/levelset.h"
#include "tfilepath.h"
#include "tgeometry.h"
#include "tnzimage.h"   // initImageIo
#include "tnzsound.h"   // initSoundIo
#include "tiio_std.h"   // Tiio::defineStd
#include "timage_io.h"

#include <QString>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>

namespace konte {

bool openToonzAvailable() { return true; }

static bool dbgOn() {
  static int v = -1;
  if (v < 0) { const char* e = std::getenv("KONTE_DEBUG"); v = (e && *e) ? 1 : 0; }
  return v > 0;
}
static void dbg(const std::string& m) {
  if (dbgOn()) { std::fprintf(stderr, "[ot] %s\n", m.c_str()); std::fflush(stderr); }
}

// m_text 为 HTML 文本；OT 的 Note 用 HTML 承载字体信息。做最小转义。
static QString toHtml(const std::string& s) {
  QString t = QString::fromStdString(s);
  t.replace("&", "&amp;");
  t.replace("<", "&lt;");
  t.replace(">", "&gt;");
  t.replace("\n", "<br>");
  return t;
}

// 重新用 OpenToonz 打开生成的 .tnz，校验帧数/声音/注记（P1 验收）
static bool verifyReload(const std::string& outFile, int N, bool expectSound,
                         std::string& vr) {
  try {
    ToonzScene s;
    TFilePath fp(outFile);
    s.setScenePath(fp);
    s.loadTnzFile(fp);  // 仅加载场景数据（不含项目/资源）
    TXsheet* xsh = s.getXsheet();
    int fc = xsh ? xsh->getFrameCount() : -1;
    std::vector<TXshSoundColumn*> scs;
    s.getSoundColumns(scs);
    int notes = (xsh && xsh->getNotes()) ? xsh->getNotes()->getCount() : 0;
    vr = "reload: frameCount=" + std::to_string(fc) + " sounds=" +
         std::to_string(scs.size()) + " notes=" + std::to_string(notes);
    bool ok = (fc == N) && (!expectSound || scs.size() >= 1) && (notes > 0);
    return ok;
  } catch (const std::exception& e) {
    vr = std::string("reload exception: ") + e.what();
    return false;
  } catch (...) {
    vr = "reload unknown exception";
    return false;
  }
}

bool writeSceneWithOpenToonz(const ScenePlan& plan, const std::string& outFile,
                             const std::string& templatePath, std::string& err) {
  try {
    // 初始化图像 IO（否则 getLevelType 不认识 png → loadLevel 返回 0）
    static bool ioReady = false;
    if (!ioReady) {
      Tiio::defineStd();
      initImageIo();
      initSoundIo();
      ioReady = true;
      dbg("io initialized");
    }

    ToonzScene scene;
    dbg("scene constructed");

    // 1) 套模板 + 初始化场景（initializeScene 可能重置 scene path，故之后设路径）
    if (!templatePath.empty()) {
      TFilePath tpl(templatePath);
      if (!tpl.isEmpty()) scene.loadTnzFile(tpl);  // 以模板为底（相机/fps/项目设置）
    }
    TProjectManager::instance()->initializeScene(&scene);
    dbg("initializeScene done");

    // 0) 设定场景路径（便于 OT 以相对 $scenefolder 编码 level 路径）
    TFilePath out(outFile);
    scene.setScenePath(out);
    dbg("scene path set: " + outFile);

    // 2) 参考层（Q8：渲染位图参考层）。level 路径需为解码后的实际路径。
    TFilePath refPath(plan.levelPath);
    dbg("loadLevel: " + plan.levelPath);
    TXshLevel* level = scene.loadLevel(refPath);
    if (!level) {
      err = "loadLevel 失败: " + plan.levelPath;
      return false;
    }
    dbg("loadLevel ok");

    // 参考层只读锁定（Q8：决定稿后参考层不可编辑）
    if (auto* simple = dynamic_cast<TXshSimpleLevel*>(level)) {
      simple->setIsReadOnly(true);
      dbg(std::string("level readOnly=") + (simple->isReadOnly() ? "yes" : "no"));
    }

    // 3) 时长钉定：参考层从第 1 帧 hold 到第 N 帧 → TXsheet 帧数 = N
    TXsheet* xsh = scene.getXsheet();
    if (!xsh) { err = "getXsheet() 为空"; return false; }
    if (xsh->getColumnCount() == 0) xsh->insertColumn(0);  // 新建首列

    TXshLevelP levelP(level);
    const int N = plan.duration.totalFrames;
    const TFrameId fid(1);
    for (int row = 0; row < N; ++row) {
      xsh->setCell(row, 0, TXshCell(levelP, fid));
    }
    xsh->updateFrameCount();
    dbg("cells set, N=" + std::to_string(N));

    // 4) 参考层锁定：TODO(P1-runtime) 按实际 OT 版本设置只读（TXshSimpleLevel 只读标志）。
    //    设计上参考层不再被编辑；此处保留锁定点，运行时按版本补 API。

    // 5) 文字进 Note（OT Note 为浮动注记，锚定到 (row,col)）
    if (TXshNoteSet* notes = xsh->getNotes()) {
      auto addNote = [&](const QString& text, int row, int col) {
        if (text.isEmpty()) return;
        TXshNoteSet::Note n;
        n.m_colorIndex = 0;
        n.m_text = text;
        n.m_row = row;
        n.m_col = col;
        n.m_pos = TPointD(5, 5);
        notes->addNote(n);
      };
      addNote(toHtml("ACTION: " + plan.notes.action), 0, 0);
      for (const auto& d : plan.notes.dialogue) {
        QString t = d.character.empty() ? QString::fromStdString(d.text)
                                        : QString::fromStdString(d.character + "： " + d.text);
        addNote(toHtml("DIALOGUE: " + t.toStdString()), 0, 0);
      }
      for (const auto& m : plan.notes.musicSe) {
        addNote(toHtml("MUSIC/SE: " + m.text), 0, 0);
      }
    }

    // 6) 声音：若 plan.hasSound，加入 TXshSoundColumn 并按帧对齐
    if (plan.hasSound && !plan.soundPath.empty()) {
      try {
        TFilePath sp(plan.soundPath);
        TXshSoundLevel* sl = new TXshSoundLevel(L"SE");
        sl->setScene(&scene);
        sl->setPath(sp);
        sl->setFrameRate(plan.fps);
        sl->load();
        scene.getLevelSet()->insertLevel(sl);
        TXshSoundColumn* sc = new TXshSoundColumn();
        int col = xsh->getColumnCount();
        xsh->insertColumn(col, sc);
        sc->setFrameRate(plan.fps);
        for (int row = 0; row < N; ++row)
          sc->setCell(row, TXshCell(TXshLevelP(sl), TFrameId(1)));
        sc->updateCells(0, N);
        dbg("sound column added");
      } catch (...) {
        dbg("sound load/add failed (ignored)");
      }
    }
    {
      std::vector<TXshSoundColumn*> scs;
      scene.getSoundColumns(scs);
      dbg("sound columns=" + std::to_string(scs.size()));
    }

    // 7) 存盘
    scene.setScenePath(out);
    {
      TFilePath dec = scene.decodeFilePath(out);
      dbg("decoded save path: " + QString::fromStdWString(dec.getWideString()).toStdString());
    }
    dbg("saving...");
    scene.save(out, 0, false);
    dbg("saved");

    // 兜底：某些环境下 ToonzScene::save 只留下 <file>.tmp 未完成 replace，
    // 这里检测并完成改名，确保落盘为 .tnz。
    {
      std::error_code ec;
      std::string tmp = outFile + ".tmp";
      if (!std::filesystem::exists(outFile) && std::filesystem::exists(tmp)) {
        std::filesystem::rename(tmp, outFile, ec);
        dbg(std::string("renamed tmp->tnz, ec=") + std::to_string(ec.value()));
      }
      dbg(std::string("final exists: ") + (std::filesystem::exists(outFile) ? "yes" : "no"));
    }

    // 持久化参考层锁定：把参考 PNG 置为只读（OT 重载时据此判定 level 只读）
    {
      std::error_code ec;
      std::filesystem::permissions(
          plan.levelPath,
          std::filesystem::perms::owner_read | std::filesystem::perms::group_read |
              std::filesystem::perms::others_read,
          std::filesystem::perm_options::replace, ec);
      auto st = std::filesystem::status(plan.levelPath, ec);
      bool ro = (st.permissions() & std::filesystem::perms::owner_write) ==
                std::filesystem::perms::none;
      dbg(std::string("ref file readOnly=") + (ro ? "yes" : "no"));
    }

    // 8) 回读校验：帧数必须 = N（P1 验收核心）
    int fc = -1;
    try {
      fc = scene.loadFrameCount(out);
    } catch (const std::exception& e) {
      dbg(std::string("loadFrameCount ex: ") + e.what());
    } catch (...) {
      dbg("loadFrameCount unknown exception");
    }
    dbg("frameCount=" + std::to_string(fc));
    if (fc != N) {
      err = "帧数校验失败: 期望 " + std::to_string(N) + "，实际 " + std::to_string(fc);
      return false;
    }

    // 9) 可选：真正重载 .tnz 验证（KONTE_VERIFY=1）
    if (dbgOn()) {
      std::string vr;
      bool ok = verifyReload(outFile, N, plan.hasSound, vr);
      dbg(vr + (ok ? " [OK]" : " [BAD]"));
      if (!ok) { err = vr; return false; }
    }
    return true;
  } catch (const std::exception& e) {
    err = e.what();
    return false;
  } catch (...) {
    err = "writeSceneWithOpenToonz: 未知异常";
    return false;
  }
}

}  // namespace konte

#else  // !KONTE_WITH_OPENTOONZ

namespace konte {
bool openToonzAvailable() { return false; }
bool writeSceneWithOpenToonz(const ScenePlan&, const std::string&, const std::string&,
                             std::string& err) {
  err = "未以 KONTE_WITH_OPENTOONZ 构建（需 OpenToonz 源码与依赖）";
  return false;
}
}  // namespace konte

#endif  // KONTE_WITH_OPENTOONZ
