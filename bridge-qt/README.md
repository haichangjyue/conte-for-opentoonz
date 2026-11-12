# konte-bridge-qt —— Bridge 的 Qt5 原生内嵌服务（生产化原型）

把 Bridge HTTP/WebSocket 服务**内嵌进 Qt 事件循环**（`QTcpServer`），便于桌面端直接托管，
无需额外的 Python sidecar 进程。本机 Qt 未装 QtWebSockets，因此 WebSocket 为手写握手/帧（RFC6455 最小集）。

## 构建

```powershell
# 需要 MSVC cl + Qt5 Core/Network（本机 X:\agent\tools\Qt\5.15.2\msvc2019_64）
powershell -NoProfile -ExecutionPolicy Bypass -File ..\scripts\build_bridge_qt.ps1
# 产物：repos\konte-for-opentoonz\build\bridge-qt\konte-bridge-qt.exe（+ Qt5Core.dll/Qt5Network.dll）
```

## 运行

```powershell
build\bridge-qt\konte-bridge-qt.exe --project ..\poc\examples\EP01\konte.json `
  --host 127.0.0.1 --port 17890 --pin 482913 `
  --py <python.exe> --poc ..\poc        # --py/--poc 仅用于 /api/export 调 Python 导出
```

## 已实现端点（最小可用子集）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 存活探针（uptime/tokens/jobs/clients） |
| POST | `/api/pair` | PIN→token（含 `expiresIn`；失败 5 次/60s → 429） |
| GET | `/api/project` | 项目元信息 |
| GET | `/api/cuts` | cut 摘要（`{items:[...]}`） |
| GET/PUT | `/api/cuts/{id}` | 读/改（`expectedRevision` 乐观锁，409） |
| POST/DELETE | `/api/cuts/{id}/lock` | 编辑锁（`{"ttl":N}`，过期自愈） |
| POST | `/api/cuts/{id}/drawing` | **multipart 图片上传**：落盘 `+drawings/`、更新 konte、生成缩略图 |
| GET | `/api/cuts/{id}/thumbnail` | 缩略图（`.bridge/thumbs/{id}.png`） |
| POST | `/api/export` | 触发导出（QProcess 调 `python -m konte_poc export`） |
| GET | `/api/export/{jobId}` | 任务状态/产物 |
| WS | `/ws` | 握手 + `cutUpdated`/`takeover`/`exportProgress` 广播 |

**图片上传**：`POST /api/cuts/{id}/drawing` 为 `multipart/form-data`（字段 `image` + 可选 `frameKind`），
服务端用 `QImage` 校验/落盘 PNG 并生成 640 长边缩略图；需 `QT_PLUGIN_PATH` 指向 Qt `plugins`（含 imageformats）。
其余未实现端点可继续沿用 Python Bridge。

## 测试

```powershell
cd bridge-qt
$env:PYTHONPATH="..\poc;..\poc\tools"
python -m unittest discover -s tests -p "test_bridge_qt.py" -v
```
真实起 exe，走 health→pair→project/cuts→update→lock→WS→export（结构包）。
