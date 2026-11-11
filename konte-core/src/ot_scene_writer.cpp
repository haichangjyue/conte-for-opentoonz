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
#include "toonz/txshnoteset.h"
#include "toonz/tframeid.h"
#include "tfilepath.h"
#include "tgeometry.h"

#include <QString>

namespace konte {

bool openToonzAvailable() { return true; }

// m_text 为 HTML 文本；OT 的 Note 用 HTML 承载字体信息。做最小转义。
static QString toHtml(const std::string& s) {
  QString t = QString::fromStdString(s);
  t.replace("&", "&amp;");
  t.replace("<", "&lt;");
  t.replace(">", "&gt;");
  t.replace("\n", "<br>");
  return t;
}

bool writeSceneWithOpenToonz(const ScenePlan& plan, const std::string& outFile,
                             const std::string& templatePath, std::string& err) {
  try {
    ToonzScene scene;

    // 1) 套模板：相机尺寸 / fps
    if (!templatePath.empty()) {
      TFilePath tpl(templatePath);
      if (!tpl.isEmpty()) scene.loadTnzFile(tpl);  // 以模板为底（相机/fps/项目设置）
    }
    TProjectManager::instance()->initializeScene(&scene);

    // 2) 参考层（Q8：渲染位图参考层）。level 路径需为解码后的实际路径。
    TFilePath refPath(plan.levelPath);
    TXshLevel* level = scene.loadLevel(refPath);
    if (!level) {
      err = "loadLevel 失败: " + plan.levelPath;
      return false;
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

    // 6) 声音：TODO(P1-runtime) 若 plan.hasSound，按帧对齐加入 TXshSoundColumn。
    //    （需 TXshSoundLevel + getSoundColumns()，运行时按实际 API 落地。）

    // 7) 存盘
    TFilePath out(outFile);
    scene.setScenePath(out);
    scene.save(out);
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
