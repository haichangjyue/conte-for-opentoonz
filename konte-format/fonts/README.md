# 内置 CJK 字体（P4 字体授权）

分镜 PDF 的动态文字（CUT / ACTION / DIALOGE / MUSIC·SE / Dur. / No. / 页合计）需要
可商用的中日文字体。本目录是**随包字体**的落点，并附许可证全文。

## 选型（已锁定）

| 字体族 | 许可 | 说明 |
|---|---|---|
| **Source Han Sans（思源黑体，默认）** | SIL OFL 1.1 | **默认**：简体中文 + 假名 + 汉字全覆盖（`SourceHanSans.ttc` SC Regular=index27/Bold=index37） |
| **Noto Sans SC** | SIL OFL 1.1 | 简体中文+假名+汉字（可变字体，备用） |
| **Noto Sans JP** | SIL OFL 1.1 | 日文假名+汉字（日文纹样更地道） |

- 三者均为 **SIL Open Font License 1.1**，允许**免费商用、随软件打包分发**；许可证全文见
  同目录 `OFL-1.1.txt`。
- **Reserved Font Name**：如对字体做修改并再分发，须改名（不得继续用 “Noto”/“Source Han” 名），
  未修改直接打包不受此限。
- **随包义务**：发布安装包/交付物时，把本目录（字体文件 + `OFL-1.1.txt`）一并附带，并在
  `LICENSES.md` / 关于页列明。

## 运行时解析顺序（`konte_poc/textfit.py`）

1. 环境变量 `KONTE_FONT`（指向单个字体文件）——测试/临时替换；
2. 模板 `fonts.*.family` 指定字体族，先在**本目录**找文件，再找系统字体；
3. 回退：Source Han Sans → Noto Sans SC → Noto Sans JP → Microsoft YaHei → MS Gothic → SimSun；
4. 全缺 → PIL 内置默认（仅西文，兜底）。

> 开发机若已装 Noto Sans JP/SC（Windows `C:\Windows\Fonts\NotoSansJP-VF.ttf` 等），
> 无需把大字体文件提交进 git；**发布打包脚本**再把字体文件复制进本目录即可。
> 字体文件请勿入库大二进制（见 `.gitignore` 约定）；本目录只保留 `README.md`、
> `OFL-1.1.txt` 与 `fonts.json`。

## fonts.json

`fonts.json` 记录字体族 → 文件名/权重/许可的映射，供打包脚本与 CI 自检使用。
