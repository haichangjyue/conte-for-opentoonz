# bridge —— LAN 本地 Bridge（OpenAPI + Python 参考实现）

单作者、单项目、局域网的 sidecar：平板 Web 前端 ↔ OpenToonz 分镜编辑器。
契约见 [`bridge.openapi.yaml`](bridge.openapi.yaml)（OpenAPI 3.0.3）。本目录 `src/konte_bridge/`
是**零第三方依赖**的 Python 参考实现（`http.server` + 手写 WebSocket 帧），用于 P1 快速验证。

## 运行

```powershell
# 需 konte_poc 在 PYTHONPATH（或已 pip install 本仓 poc）
$env:PYTHONPATH = "..\poc"
python -m konte_bridge --project ..\poc\examples\EP01\konte.json `
  --host 127.0.0.1 --port 17890 --pin 482913 `
  --base-psd "X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd"
```

启动后打印监听地址与 PIN。桌面端（OT 分镜面板）展示 PIN/二维码，平板 `POST /api/pair` 换取 token。

## 接口（与 OpenAPI 一致）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/health` | 否 | 健康/存活（uptime、tokens、jobs、clients） |
| POST | `/api/pair` | 否 | PIN → token（含 `expiresIn`；失败过多 429） |
| GET | `/api/project` | 是 | 项目元信息（画幅/bleed/DPI/fps） |
| GET | `/api/cuts` | 是 | cut 摘要列表 |
| GET/PUT | `/api/cuts/{cutId}` | 是 | 读/改元数据（revision 乐观锁，冲突 409） |
| POST | `/api/cuts/{cutId}/drawing` | 是 | 上传 PNG → 落盘 `+drawings/` → 更新 konte → 缩略图 |
| POST/DELETE | `/api/cuts/{cutId}/lock` | 是 | 获取/释放编辑锁（TTL 防死锁） |
| GET | `/api/cuts/{cutId}/thumbnail` | 是 | 缩略图 PNG |
| POST | `/api/export` | 是 | 触发导出（非 final / 存在 TBD → 422） |
| GET | `/api/export/{jobId}` | 是 | 任务状态/进度/产物 |
| WS | `/ws` | — | 事件：`cutUpdated`/`thumbnailReady`/`exportProgress`/`takeover` |

## 安全 / 生产化

- 仅监听 `127.0.0.1`/LAN；`Bearer token` 绑定会话，**默认 12h 过期**（`--token-ttl`，过期返回 401 `TOKEN_EXPIRED`）。
- 上传**单次限 10MB**（`--max-upload-mb`），并按设备**限速**（默认 60 次/分钟，`--max-uploads-per-min`，超限 429 `RATE_LIMITED`）；图片用 Pillow 校验。
- **PIN 暴力尝试限制**：同一客户端 60s 内失败 5 次即 429 `PAIR_LOCKED`（可配）。
- cut 级锁（默认 TTL 120s，可按请求 `{"ttl": N}` 覆盖；过期自动视为未锁）+ `revision` 乐观锁。
- **导出任务保留**：默认 1h / 上限 50（`--job-ttl`/`--max-jobs`），自动清理。
- `/api/health` 供桌面 sidecar 生命周期/看门狗探活（零鉴权）。
- 响应带 `Cache-Control: no-store`。

## Qt 原生内嵌实现（生产化原型）

另见 [`../bridge-qt/`](../bridge-qt/README.md)：`konte-bridge-qt`（C++17 + Qt5 Core/Network，QTcpServer）
把同一套 HTTP/WS 服务内嵌进 Qt 事件循环，桌面端可直接托管、无需 Python sidecar；覆盖 health/pair/
project/cuts/update/lock/drawing(图片上传)/thumbnail/export/WS。构建：`scripts/build_bridge_qt.ps1`。

## 测试

```powershell
cd bridge
python -m unittest discover -s tests -p "smoke_test.py" -v
```
冒烟测试会真实起服务，走配对→读→改→锁→上传画面→导出→WS 握手全链路；
另有 `test_hardening.py` 覆盖 token TTL / 上传限速 / PIN 锁定 / 锁过期 / 任务清理 / health。
