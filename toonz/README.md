# toonz/ —— OpenToonz 源码位置

把 **OpenToonz fork 源码**放在此目录，或作为 git submodule：

```bash
git submodule add https://github.com/opentoonz/opentoonz.git toonz
git -C toonz remote add upstream https://github.com/opentoonz/opentoonz.git 2>/dev/null || true
```

- 保留上游 `LICENSE` / `NOTICE`（BSD-3）。
- 集成层新增代码放 `toonz/sources/toonz/konte/`（导出命令接线、面板宿主）。
