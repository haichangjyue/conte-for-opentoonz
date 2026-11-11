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
| POST | `/api/pair` | 否 | PIN → token |
| GET | `/api/project` | 是 | 项目元信息（画幅/bleed/DPI/fps） |
| GET | `/api/cuts` | 是 | cut 摘要列表 |
| GET/PUT | `/api/cuts/{cutId}` | 是 | 读/改元数据（revision 乐观锁，冲突 409） |
| POST | `/api/cuts/{cutId}/drawing` | 是 | 上传 PNG → 落盘 `+drawings/` → 更新 konte → 缩略图 |
| POST/DELETE | `/api/cuts/{cutId}/lock` | 是 | 获取/释放编辑锁（TTL 防死锁） |
| GET | `/api/cuts/{cutId}/thumbnail` | 是 | 缩略图 PNG |
| POST | `/api/export` | 是 | 触发导出（非 final / 存在 TBD → 422） |
| GET | `/api/export/{jobId}` | 是 | 任务状态/进度/产物 |
| WS | `/ws` | — | 事件：`cutUpdated`/`thumbnailReady`/`exportProgress`/`takeover` |

## 安全

- 仅监听 `127.0.0.1`/LAN；`Bearer token` 绑定会话。
- 上传限 10MB；图片用 Pillow 校验。
- cut 级锁（默认 TTL 120s）+ `revision` 乐观锁，避免同一项目双开会话互相覆盖。

## 测试

```powershell
cd bridge
python -m unittest discover -s tests -p "smoke_test.py" -v
```
冒烟测试会真实起服务，走配对→读→改→锁→上传画面→导出→WS 握手全链路（9 项）。
