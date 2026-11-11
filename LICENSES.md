# 许可证与合规清单（LICENSES）

> 交接用。产品基于 OpenToonz（BSD-3-Clause）二次开发，需遵守各方许可证。
> 本清单为**初始版**，标注 [待审计] 的须在发布前逐项核对并补全。

## 0. 许可证分层（Open-core 策略，决策 D9）

| 组件 | 开源/闭源 | 许可证 |
|---|---|---|
| OpenToonz fork + 集成层 | 开源 | BSD-3-Clause（沿用 OT，附 NOTICE） |
| 导出内核（`.tnz` / A4 PDF / 打包） | 开源 | BSD-3-Clause |
| `konte.schema.json` / manifest / Bridge API + sidecar 参考实现 | 开源 | 代码 BSD-3；规范文档 CC-BY-4.0 |
| 分镜编辑器 UX（桌面 C++ 面板 / Web 前端） | **闭源** | 专有 |
| 云 / 实时协作 / 制作管理 / 企业功能 | **闭源** | 专有 |
| 打包部署工具、品牌/模板包 | 闭源 | 专有 |

- **发行方式**：组合构建（BSD 部分 + 专有模块）；BSD 部分附 `NOTICE`，专有部分单独声明；**品牌自有，不暗示 OpenToonz 官方背书**。
- **仓库**：Repo1 开源（OT fork + 导出/格式/Bridge）；Repo2 私有（编辑器 UX + 企业）。


## 1. OpenToonz 核心
- **许可证**：BSD-3-Clause（"New"/"Revised"）。来源：仓库 `LICENSE.txt`。
- **义务**：
  1. 保留版权声明、许可条款、免责声明；
  2. 二进制分发需在文档/材料中附同样声明；
  3. **不得**用版权人/贡献者名义为衍生产品背书（未经书面许可）。
- **允许**：商用、闭源分发、修改、fork。→ 本项目可闭源商用。

## 2. OpenToonz 内部特殊目录 [待审计]
| 范围 | 来源 | 说明 |
|---|---|---|
| `thirdparty/` | 各第三方库 | 按各自 README/源码许可证（如 Qt、OpenCV、Boost、libmypaint 等），需逐一登记 |
| `stuff/library/mypaint brushes/` | 见其 `Licenses.txt` | 笔刷授权各异 |
| `stuff/doc/Tahoma2D-LICENSE.txt` | Tahoma2D 移植部分 | 按其声明 |
| Qt5 / OpenCV / Boost 等 | LGPL/BSD/Apache 等 | 动态/静态链接义务不同，需法务确认 |

## 3. 本项目新增依赖 [待审计]
| 组件 | 用途 | 许可证（初判） |
|---|---|---|
| nlohmann/json | konte.json 读写 | MIT |
| Bridge sidecar 运行时（Node/Python） | 本地服务 | MIT/PSF 等（按运行时） |
| PDF 生成库 | A4 叠图 | 按选型（如 reportlab BSD / pdf-lib MIT） |
| **CJK 字体**（内置） | 分镜 PDF 文字 | **需可商用授权**：建议 Noto Sans CJK / Source Han Sans（SIL OFL）——发布前锁定并附 OFL |

## 4. 待办
- [ ] 生成 `thirdparty/` 全量许可证清单（脚本扫描 + 人工核对）。
- [ ] 确认 CJK 字体选型与授权，随包附许可证。
- [ ] Qt 链接方式（动态/静态）合规确认。
- [ ] 在安装包/关于页附总 `NOTICE`/`LICENSES.txt`。

> 结论：核心 **BSD-3 允许闭源商用**；风险点集中在 `thirdparty/`、字体、Qt 链接方式——发布前按上表审计即可。
