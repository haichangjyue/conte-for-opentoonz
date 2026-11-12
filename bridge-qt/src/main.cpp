// SPDX-License-Identifier: BSD-3-Clause
// konte-bridge-qt —— Bridge sidecar 的 Qt5 原生内嵌实现（最小可用子集）。
//
// 目的（生产化）：把 Bridge 服务内嵌进 Qt 事件循环（QTcpServer），便于桌面端直接托管，
// 无需外部 Python 进程。实现 HTTP/1.1 子集 + 手写 WebSocket 握手/帧广播（本机 Qt 未装 QtWebSockets）。
//
// 覆盖：/api/health、/api/pair、/api/project、/api/cuts、GET/PUT /api/cuts/{id}、
//       POST/DELETE /api/cuts/{id}/lock、GET /api/cuts/{id}/thumbnail、POST /api/export、
//       GET /api/export/{jobId}、/ws。图片上传(drawing)在 Qt 版返回 501（请用 Python Bridge）。
//
// 构建：scripts/build_bridge_qt.ps1（cl + Qt5 Core/Network，无需 moc）。
// 运行：konte-bridge-qt --project <konte.json> [--host 127.0.0.1] [--port 17890] [--pin 482913]

#include <QtCore/QCoreApplication>
#include <QtCore/QCommandLineParser>
#include <QtCore/QCryptographicHash>
#include <QtCore/QDateTime>
#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QList>
#include <QtCore/QMap>
#include <QtCore/QProcess>
#include <QtCore/QProcessEnvironment>
#include <QtCore/QRandomGenerator>
#include <QtCore/QRegularExpression>
#include <QtCore/QSaveFile>
#include <QtCore/QSet>
#include <QtCore/QTimer>
#include <QtCore/QUuid>
#include <QtGui/QImage>
#include <QtNetwork/QHostAddress>
#include <QtNetwork/QTcpServer>
#include <QtNetwork/QTcpSocket>

#include <algorithm>

static QString nowIso() { return QDateTime::currentDateTime().toString(Qt::ISODate); }
static qint64 nowMs() { return QDateTime::currentMSecsSinceEpoch(); }

// ---- WebSocket 最小帧（文本/关闭/ping）----
static QByteArray wsFrame(int opcode, const QByteArray &payload) {
    QByteArray f;
    f.append(char(0x80 | (opcode & 0x0F)));
    int n = payload.size();
    if (n < 126) {
        f.append(char(n));
    } else if (n < 65536) {
        f.append(char(126));
        f.append(char((n >> 8) & 0xFF));
        f.append(char(n & 0xFF));
    } else {
        f.append(char(127));
        for (int i = 7; i >= 0; --i) f.append(char((n >> (8 * i)) & 0xFF));
    }
    f.append(payload);
    return f;
}

static QString wsAccept(const QByteArray &key) {
    QByteArray data = key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    QByteArray sha = QCryptographicHash::hash(data, QCryptographicHash::Sha1);
    return QString::fromLatin1(sha.toBase64());
}

// multipart/form-data 解析（只取字段名与 image 二进制）
static void parseMultipart(const QByteArray &body, const QString &boundary,
                           QMap<QString, QString> &fields, QByteArray &image) {
    QByteArray delim = "--" + boundary.toUtf8();
    int pos = 0;
    while (true) {
        int start = body.indexOf(delim, pos);
        if (start < 0) break;
        start += delim.size();
        if (body.mid(start, 2) == "--") break;
        if (body.mid(start, 2) == "\r\n") start += 2;
        int next = body.indexOf(delim, start);
        if (next < 0) break;
        QByteArray part = body.mid(start, next - start);
        int hEnd = part.indexOf("\r\n\r\n");
        if (hEnd >= 0) {
            QByteArray head = part.left(hEnd);
            QByteArray data = part.mid(hEnd + 4);
            if (data.endsWith("\r\n")) data.chop(2);
            int n = head.indexOf("name=\"");
            if (n >= 0) {
                n += 6;
                int e = head.indexOf('"', n);
                QString name = QString::fromUtf8(head.mid(n, e - n));
                if (name == "image") image = data;
                else fields[name] = QString::fromUtf8(data);
            }
        }
        pos = next;
    }
}

class BridgeServer : public QTcpServer {
public:
    BridgeServer(QString projectPath, QString pin, QString py, QString pocPath, QObject *parent = nullptr)
        : QTcpServer(parent), m_projectPath(std::move(projectPath)), m_pin(std::move(pin)),
          m_py(std::move(py)), m_pocPath(std::move(pocPath)), m_started(nowMs()) {}

    // 便于测试/观察
    int wsCount() const { return m_ws.size(); }
    void setProjectTitle(const QString &t) { m_projectTitle = t; }

protected:
    void incomingConnection(qintptr fd) override {
        auto *s = new QTcpSocket(this);
        s->setSocketDescriptor(fd);
        auto *buf = new QByteArray();
        connect(s, &QTcpSocket::readyRead, this, [this, s, buf]() { onReadable(s, buf); });
        connect(s, &QTcpSocket::disconnected, this, [this, s, buf]() {
            m_ws.removeAll(s);
            delete buf;
            s->deleteLater();
        });
    }

private:
    // ---------------- HTTP 解析 ----------------
    void onReadable(QTcpSocket *s, QByteArray *buf) {
        if (s->property("ws").toBool()) {
            QByteArray data = s->readAll();
            // 简易处理：close(0x8) 断开；ping(0x9) 回 pong
            if (data.size() >= 2) {
                int opcode = (unsigned char)data[0] & 0x0F;
                if (opcode == 0x8) s->disconnectFromHost();
                else if (opcode == 0x9) s->write(wsFrame(0xA, ""));
            }
            return;
        }
        *buf += s->readAll();
        int idx = buf->indexOf("\r\n\r\n");
        if (idx < 0) return;
        QByteArray head = buf->left(idx);
        QList<QByteArray> lines = head.split('\n');
        if (lines.isEmpty()) return;
        QList<QByteArray> first = lines[0].trimmed().split(' ');
        if (first.size() < 2) { sendError(s, 400, "BAD_REQUEST", "bad request line"); return; }
        QString method = QString::fromLatin1(first[0]);
        QString path = QString::fromLatin1(first[1]).split('?').first();
        QMap<QString, QByteArray> headers;
        for (int i = 1; i < lines.size(); ++i) {
            QByteArray ln = lines[i].trimmed();
            int c = ln.indexOf(':');
            if (c < 0) continue;
            headers[QString::fromLatin1(ln.left(c)).trimmed().toLower()] = ln.mid(c + 1).trimmed();
        }
        int clen = headers.value("content-length").toInt();
        QByteArray rest = buf->mid(idx + 4);
        if (rest.size() < clen) return;  // 等待完整 body
        QByteArray body = rest.left(clen);
        buf->clear();
        handle(s, method, path, headers, body);
    }

    void sendJson(QTcpSocket *s, const QJsonObject &obj, int status = 200) {
        QString reason = status == 200 ? "OK" : status == 201 ? "Created" : status == 202 ? "Accepted" :
                         status == 204 ? "No Content" : status == 400 ? "Bad Request" :
                         status == 401 ? "Unauthorized" : status == 404 ? "Not Found" :
                         status == 409 ? "Conflict" : status == 422 ? "Unprocessable" :
                         status == 429 ? "Too Many Requests" : status == 501 ? "Not Implemented" : "Error";
        QByteArray payload = (status == 204) ? QByteArray() : QJsonDocument(obj).toJson(QJsonDocument::Compact);
        QByteArray resp = QString("HTTP/1.1 %1 %2\r\n").arg(status).arg(reason).toUtf8();
        resp += "Content-Type: application/json; charset=utf-8\r\n";
        resp += "Content-Length: " + QByteArray::number(payload.size()) + "\r\n";
        resp += "Cache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n";
        resp += payload;
        s->write(resp);
        s->disconnectFromHost();
    }
    void sendError(QTcpSocket *s, int status, const QString &code, const QString &msg) {
        QJsonObject o{{"code", code}, {"message", msg}};
        sendJson(s, o, status);
    }

    // ---------------- 项目 JSON ----------------
    QJsonObject loadDoc() {
        QFile f(m_projectPath);
        if (!f.open(QIODevice::ReadOnly)) return {};
        return QJsonDocument::fromJson(f.readAll()).object();
    }
    bool saveDoc(const QJsonObject &doc) {
        QSaveFile f(m_projectPath);
        if (!f.open(QIODevice::WriteOnly)) return false;
        f.write(QJsonDocument(doc).toJson(QJsonDocument::Indented));
        return f.commit();
    }
    QJsonArray cutsOf(QJsonObject &doc) { return doc.value("cuts").toArray(); }
    int findCut(QJsonArray &cuts, const QString &id) {
        for (int i = 0; i < cuts.size(); ++i)
            if (cuts[i].toObject().value("id").toString() == id) return i;
        return -1;
    }
    void replaceCut(QJsonObject &doc, int idx, const QJsonObject &cut) {
        QJsonArray arr = doc.value("cuts").toArray();
        arr[idx] = cut;
        doc["cuts"] = arr;
    }

    // 画布尺寸 = 分镜 PICTURE 格子（扣 inset）的宽高比（与 PDF 单元格一致，WYSIWYG）
    QJsonObject computeCanvas(const QJsonObject &p) {
        QJsonObject def{{"width", 1920}, {"height", 1080}, {"aspect", 1920.0 / 1080.0}};
        QString id = p.value("pdfTemplate").toString("scfilms_storyboard");
        QString repoRoot = QFileInfo(m_pocPath).absolutePath();
        QString path = repoRoot + "/konte-format/templates/" + id + ".json";
        QFile f(path);
        if (!f.open(QIODevice::ReadOnly)) return def;
        QJsonObject t = QJsonDocument::fromJson(f.readAll()).object();
        QJsonObject col = t.value("columns").toObject().value("picture").toObject();
        double x0 = col.value("x0").toDouble(), x1 = col.value("x1").toDouble();
        int inset = t.value("picture").toObject().value("inset").toInt(0);
        QJsonArray cuts = t.value("rows").toObject().value("cuts").toArray();
        if (cuts.isEmpty()) return def;
        double sum = 0;
        for (auto r : cuts)
            sum += r.toObject().value("y1").toDouble() - r.toObject().value("y0").toDouble();
        double h = sum / cuts.size() - 2 * inset;
        double w = (x1 - x0) - 2 * inset;
        if (w > 0 && h > 0) {
            double W = 1920.0, H = W * h / w;
            return QJsonObject{{"width", int(qRound(W))}, {"height", int(qRound(H))},
                               {"aspect", w / h}};
        }
        return def;
    }

    // ---------------- 鉴权 ----------------
    bool auth(QTcpSocket *s, const QMap<QString, QByteArray> &headers, QString *deviceId) {
        QString h = QString::fromUtf8(headers.value("authorization"));
        if (!h.startsWith("Bearer ")) { sendError(s, 401, "UNAUTHORIZED", "token 缺失或无效"); return false; }
        QString tok = h.mid(7).trimmed();
        auto it = m_tokens.find(tok);
        if (it == m_tokens.end()) { sendError(s, 401, "UNAUTHORIZED", "token 缺失或无效"); return false; }
        QJsonObject info = it.value();
        if (info.value("expiresAt").toDouble() <= nowMs()) {
            m_tokens.erase(it);
            sendError(s, 401, "TOKEN_EXPIRED", "token 已过期，请重新配对");
            return false;
        }
        if (deviceId) *deviceId = info.value("deviceId").toString();
        return true;
    }

    // ---------------- 路由 ----------------
    void handle(QTcpSocket *s, const QString &method, const QString &path,
                const QMap<QString, QByteArray> &headers, const QByteArray &body) {
        if (method == "OPTIONS") {
            QByteArray resp =
                "HTTP/1.1 204 No Content\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Access-Control-Allow-Methods: GET,POST,PUT,DELETE,OPTIONS\r\n"
                "Access-Control-Allow-Headers: Authorization,Content-Type\r\n"
                "Access-Control-Allow-Private-Network: true\r\n"
                "Content-Length: 0\r\nConnection: close\r\n\r\n";
            s->write(resp);
            s->disconnectFromHost();
            return;
        }
        if (path == "/ws") { doWs(s, headers); return; }
        QJsonObject jbody = QJsonDocument::fromJson(body).object();

        if (path == "/api/health" && method == "GET") {
            QJsonObject o{{"ok", true},
                          {"uptimeSec", double(nowMs() - m_started) / 1000.0},
                          {"tokens", m_tokens.size()},
                          {"jobs", m_jobs.size()},
                          {"clients", m_ws.size()},
                          {"project", m_projectTitle}};
            sendJson(s, o); return;
        }
        if (path == "/api/pair" && method == "POST") {
            QString client = s->peerAddress().toString();
            qint64 now = nowMs();
            QList<qint64> &fails = m_pairFails[client];
            while (!fails.isEmpty() && now - fails.first() > m_pairWindowMs) fails.removeFirst();
            if (fails.size() >= m_maxPairFail) { sendError(s, 429, "PAIR_LOCKED", "PIN 尝试过于频繁"); return; }
            if (jbody.value("pin").toString() != m_pin) {
                fails.append(now);
                sendError(s, 401, "BAD_PIN", "PIN 无效"); return;
            }
            fails.clear();
            QString token = QUuid::createUuid().toString(QUuid::WithoutBraces) + QUuid::createUuid().toString(QUuid::WithoutBraces);
            QString deviceId = "dev-" + QUuid::createUuid().toString(QUuid::WithoutBraces).left(8);
            QJsonObject info{{"deviceId", deviceId},
                             {"deviceName", jbody.value("deviceName").toString("device")},
                             {"at", nowIso()},
                             {"expiresAt", double(now + m_tokenTtlMs)}};
            m_tokens[token] = info;
            QJsonObject o{{"token", token}, {"projectId", m_projectTitle},
                          {"deviceId", deviceId}, {"expiresIn", int(m_tokenTtlMs / 1000)}};
            sendJson(s, o); return;
        }

        // 其余全部需鉴权
        QString deviceId;
        if (!auth(s, headers, &deviceId)) return;

        if (path == "/api/project" && method == "GET") {
            QJsonObject doc = loadDoc();
            QJsonObject p = doc.value("project").toObject();
            QJsonObject o{{"projectId", p.value("title").toString("project")},
                          {"title", p.value("title").toString()},
                          {"status", p.value("status").toString()},
                          {"fps", p.value("fps").toInt()},
                          {"frame", p.value("frame")},
                          {"bleed", p.value("bleed")},
                          {"cameraBox", p.value("cameraBox")},
                          {"template", p.value("template")},
                          {"canvas", computeCanvas(p)}};
            sendJson(s, o); return;
        }
        if (path == "/api/cuts" && method == "GET") {
            QJsonObject doc = loadDoc();
            QJsonArray cuts = cutsOf(doc);
            QVector<QJsonObject> v;
            for (auto c : cuts) v.push_back(c.toObject());
            std::sort(v.begin(), v.end(), [](const QJsonObject &a, const QJsonObject &b) {
                return a.value("order").toInt() < b.value("order").toInt();
            });
            QJsonArray out;
            for (auto &c : v) {
                QJsonObject layer = c.value("layout").toObject();
                QJsonObject dur = c.value("duration").toObject();
                out.append(QJsonObject{{"id", c.value("id")}, {"scene", c.value("scene")},
                                       {"cut", c.value("cut")}, {"number", c.value("number")},
                                       {"order", c.value("order")},
                                       {"state", c.value("state")},
                                       {"durationStatus", dur.value("status")},
                                       {"seconds", dur.value("seconds")},
                                       {"frames", dur.value("frames")},
                                       {"totalFrames", dur.value("totalFrames")},
                                       {"page", layer.value("page").isDouble() ? layer.value("page") : c.value("page")},
                                       {"rowSpan", layer.value("rowSpan")},
                                       {"panelCount", c.value("drawings").toArray().size()},
                                       {"thumbnailUrl", QString("/api/cuts/%1/thumbnail").arg(c.value("id").toString())}});
            }
            sendJson(s, QJsonObject{{"items", out}}); return;
        }

        if (path == "/api/cuts" && method == "POST") {
            QJsonObject doc = loadDoc();
            QJsonObject proj = doc.value("project").toObject();
            QJsonArray cuts = cutsOf(doc);
            int maxNum = 0, maxOrder = 0, maxPage = 0;
            for (auto cv : cuts) {
                QJsonObject c = cv.toObject();
                maxNum = qMax(maxNum, c.value("number").toInt());
                maxOrder = qMax(maxOrder, c.value("order").toInt());
                QJsonObject lay = c.value("layout").toObject();
                int pg = lay.value("page").isDouble() ? lay.value("page").toInt() : c.value("page").toInt();
                maxPage = qMax(maxPage, pg);
            }
            int num = maxNum + 1;
            QString title = proj.value("title").toString("scene");
            QString scene = title;
            QString slug = title.toLower();
            slug.replace(QRegularExpression("[^a-z0-9]+"), "");
            if (slug.isEmpty()) slug = "scene";
            QString label = QString::number(num);  // CUT 号纯数字
            QString id = QString("%1-c%2").arg(slug).arg(num, 3, 10, QChar('0'));
            while (findCut(cuts, id) >= 0) id += "-x";
            int order = maxOrder + 1;
            QString seq;
            QJsonArray seqs = doc.value("sequences").toArray();
            if (!seqs.isEmpty()) seq = seqs[0].toObject().value("id").toString();
            int fps = proj.value("fps").toInt(24);
            QJsonObject frame = proj.value("frame").toObject();
            int w = frame.value("width").toInt(1920), h = frame.value("height").toInt(1080);
            QString projectDir = QFileInfo(m_projectPath).absolutePath();
            QString stem = QString("%1_%2_p0_r1").arg(scene).arg(label);
            QString relDir = "+drawings/konte/" + stem;
            QDir(projectDir).mkpath(relDir);
            QImage blank(1920, 1080, QImage::Format_RGB888);
            blank.fill(Qt::white);
            blank.save(projectDir + "/" + relDir + "/panel.png", "PNG");
            QJsonObject drawing{{"id", label + "-d1"}, {"role", "panel"},
                                {"level", relDir + "/panel.png"}, {"source", "web"},
                                {"deviceId", "web"}, {"revision", 1}, {"updatedAt", nowIso()}};
            QJsonObject cut{{"id", id},
                            {"sequenceId", seq.isEmpty() ? QJsonValue() : QJsonValue(seq)},
                            {"scene", scene}, {"cut", label}, {"number", num}, {"order", order},
                            {"duration", QJsonObject{{"status", "fixed"}, {"seconds", 2},
                                                     {"frames", 0}, {"totalFrames", 2 * fps}}},
                            {"frame", QJsonObject{{"kind", "standard"},
                                                  {"rect", QJsonObject{{"x", 0}, {"y", 0}, {"w", w}, {"h", h}}}}},
                            {"drawings", QJsonArray{drawing}},
                            {"action", ""}, {"dialogue", QJsonArray()}, {"musicSe", QJsonArray()},
                            {"audio", QJsonValue()},
                            {"camera", QJsonObject{{"note", ""}, {"keyframes", QJsonArray()}}},
                            {"state", "final"}, {"lock", QJsonValue()},
                            {"export", QJsonObject{{"status", "notExported"}, {"sceneFile", QJsonValue()}}},
                            {"revision", 1}, {"updatedAt", nowIso()}};
            cuts.append(cut);
            doc["cuts"] = cuts;
            QJsonObject meta = doc.value("meta").toObject();
            meta["updatedAt"] = nowIso();
            doc["meta"] = meta;
            saveDoc(doc);
            QDir(projectDir).mkpath(projectDir + "/.bridge/thumbs");
            QImage th = blank.scaled(640, 640, Qt::KeepAspectRatio, Qt::SmoothTransformation);
            th.save(projectDir + "/.bridge/thumbs/" + id + ".png", "PNG");
            broadcast(QJsonObject{{"event", "cutCreated"}, {"cutId", id}, {"number", num}});
            sendJson(s, QJsonObject{{"cut", cut}}, 201);
            return;
        }

        // /api/cuts/{id}[/lock|/thumbnail]
        QStringList seg = path.split('/', Qt::SkipEmptyParts);
        if (seg.size() >= 3 && seg[0] == "api" && seg[1] == "cuts") {
            QString id = seg[2];
            QString sub = seg.size() >= 4 ? seg[3] : QString();
            QJsonObject doc = loadDoc();
            QJsonArray cuts = cutsOf(doc);
            int idx = findCut(cuts, id);
            if (idx < 0) { sendError(s, 404, "NOT_FOUND", "cut 不存在: " + id); return; }
            QJsonObject cut = cuts[idx].toObject();

            if (sub.isEmpty() && method == "GET") { sendJson(s, cut); return; }
            if (sub == "drawing" && method == "POST") {
                QString ctype = QString::fromUtf8(headers.value("content-type"));
                int bi = ctype.indexOf("boundary=");
                if (bi < 0) { sendError(s, 400, "BAD_MULTIPART", "缺少 multipart boundary"); return; }
                QString boundary = ctype.mid(bi + 9).trimmed();
                if (boundary.startsWith('"') && boundary.endsWith('"'))
                    boundary = boundary.mid(1, boundary.size() - 2);
                QMap<QString, QString> fields;
                QByteArray imgBytes;
                parseMultipart(body, boundary, fields, imgBytes);
                if (imgBytes.isEmpty()) { sendError(s, 400, "NO_IMAGE", "缺少 image 文件"); return; }
                QImage img;
                if (!img.loadFromData(imgBytes)) { sendError(s, 400, "BAD_IMAGE", "上传内容不是有效图片"); return; }
                QString projectDir = QFileInfo(m_projectPath).absolutePath();
                int rev = cut.value("revision").toInt() + 1;
                QString idxRaw = fields.value("drawingIndex");
                int dindex = idxRaw.isEmpty() ? 0 : idxRaw.toInt();
                if (dindex < 0) { sendError(s, 400, "BAD_INDEX", "drawingIndex 不能为负"); return; }
                QJsonArray drawings = cut.value("drawings").toArray();
                if (dindex > drawings.size()) { sendError(s, 400, "BAD_INDEX", "drawingIndex 越界"); return; }
                QString stem = QString("%1_%2_p%3_r%4")
                                   .arg(cut.value("scene").toString("SC"))
                                   .arg(cut.value("cut").toString("C000"))
                                   .arg(dindex).arg(rev);
                QString relDir = "+drawings/konte/" + stem;
                QDir(projectDir).mkpath(relDir);
                QString imgPath = projectDir + "/" + relDir + "/panel.png";
                if (!img.convertToFormat(QImage::Format_RGB888).save(imgPath, "PNG")) {
                    sendError(s, 500, "SAVE_FAILED", "保存画面失败"); return;
                }
                QJsonObject drawing;
                if (dindex < drawings.size()) drawing = drawings[dindex].toObject();
                else drawing = QJsonObject{{"id", QString("%1-d%2").arg(cut.value("cut").toString("C")).arg(dindex + 1)},
                                           {"role", "panel"}};
                drawing["level"] = relDir + "/panel.png";
                drawing["source"] = "web";
                drawing["deviceId"] = deviceId;
                drawing["revision"] = rev;
                drawing["updatedAt"] = nowIso();
                if (dindex < drawings.size()) drawings[dindex] = drawing; else drawings.append(drawing);
                cut["drawings"] = drawings;
                if (drawings.size() > 1) {
                    QJsonObject lay = cut.value("layout").toObject();
                    if (!lay.contains("page")) lay["page"] = cut.value("page").toInt(1);
                    if (!lay.contains("rowStart")) lay["rowStart"] = 0;
                    lay["rowSpan"] = drawings.size();
                    cut["layout"] = lay;
                }
                QString fk = fields.value("frameKind");
                if (fk == "standard" || fk == "oversize") {
                    QJsonObject fr = cut.value("frame").toObject();
                    fr["kind"] = fk;
                    cut["frame"] = fr;
                }
                cut["revision"] = rev;
                cut["updatedAt"] = nowIso();
                replaceCut(doc, idx, cut);
                saveDoc(doc);
                // 缩略图（640 长边，按格）
                QString thumbDir = projectDir + "/.bridge/thumbs";
                QDir().mkpath(thumbDir);
                QImage thumb = img.scaled(640, 640, Qt::KeepAspectRatio, Qt::SmoothTransformation);
                if (dindex == 0) thumb.save(thumbDir + "/" + id + ".png", "PNG");
                thumb.save(thumbDir + "/" + id + "_" + QString::number(dindex) + ".png", "PNG");
                broadcast(QJsonObject{{"event", "thumbnailReady"}, {"cutId", id}, {"revision", rev}, {"index", dindex}});
                QJsonObject out{{"drawingId", drawing.value("id").toString()},
                                {"revision", rev}, {"index", dindex},
                                {"panelCount", drawings.size()},
                                {"thumbnailUrl", QString("/api/cuts/%1/panels/%2/thumbnail").arg(id).arg(dindex)}};
                sendJson(s, out);
                return;
            }
            if (sub == "panels" && seg.size() >= 6 && seg[5] == "thumbnail" && method == "GET") {
                int dindex = seg[4].toInt();
                QString projectDir = QFileInfo(m_projectPath).absolutePath();
                QString p = projectDir + "/.bridge/thumbs/" + id + "_" + QString::number(dindex) + ".png";
                if (!QFile::exists(p)) {
                    QJsonArray ds = cut.value("drawings").toArray();
                    if (dindex >= 0 && dindex < ds.size()) {
                        QString lv = ds[dindex].toObject().value("level").toString();
                        QString src = QFileInfo(lv).isAbsolute() ? lv : (projectDir + "/" + lv);
                        QImage img;
                        if (!lv.isEmpty() && img.load(src)) {
                            QDir().mkpath(projectDir + "/.bridge/thumbs");
                            QImage th = img.scaled(640, 640, Qt::KeepAspectRatio, Qt::SmoothTransformation);
                            th.save(p, "PNG");
                        }
                    }
                }
                QFile f(p);
                if (!f.exists()) { sendError(s, 404, "NOT_FOUND", "缩略图不存在"); return; }
                f.open(QIODevice::ReadOnly);
                QByteArray data = f.readAll();
                QByteArray resp = "HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: " +
                                  QByteArray::number(data.size()) +
                                  "\r\nCache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n" + data;
                s->write(resp); s->disconnectFromHost(); return;
            }
            if (sub == "panels" && method == "POST") {
                QJsonArray drawings = cut.value("drawings").toArray();
                int dindex = drawings.size();
                int rev = cut.value("revision").toInt() + 1;
                QString projectDir = QFileInfo(m_projectPath).absolutePath();
                QString stem = QString("%1_%2_p%3_r%4")
                                   .arg(cut.value("scene").toString("SC"))
                                   .arg(cut.value("cut").toString("C000"))
                                   .arg(dindex).arg(rev);
                QString relDir = "+drawings/konte/" + stem;
                QDir(projectDir).mkpath(relDir);
                QImage blank(1920, 1080, QImage::Format_RGB888);
                blank.fill(Qt::white);
                blank.save(projectDir + "/" + relDir + "/panel.png", "PNG");
                QJsonObject drawing{{"id", QString("%1-d%2").arg(cut.value("cut").toString("C")).arg(dindex + 1)},
                                    {"role", "panel"}, {"level", relDir + "/panel.png"},
                                    {"source", "web"}, {"deviceId", deviceId},
                                    {"revision", rev}, {"updatedAt", nowIso()}};
                drawings.append(drawing);
                cut["drawings"] = drawings;
                QJsonObject lay = cut.value("layout").toObject();
                if (!lay.contains("page")) lay["page"] = cut.value("page").toInt(1);
                if (!lay.contains("rowStart")) lay["rowStart"] = 0;
                lay["rowSpan"] = drawings.size();
                cut["layout"] = lay;
                cut["revision"] = rev;
                cut["updatedAt"] = nowIso();
                replaceCut(doc, idx, cut);
                saveDoc(doc);
                QString thumbDir = projectDir + "/.bridge/thumbs";
                QDir().mkpath(thumbDir);
                QImage th = blank.scaled(640, 640, Qt::KeepAspectRatio, Qt::SmoothTransformation);
                th.save(thumbDir + "/" + id + "_" + QString::number(dindex) + ".png", "PNG");
                broadcast(QJsonObject{{"event", "panelAdded"}, {"cutId", id}, {"index", dindex}});
                sendJson(s, QJsonObject{{"index", dindex}, {"drawing", drawing}, {"revision", rev},
                                        {"panelCount", drawings.size()},
                                        {"thumbnailUrl", QString("/api/cuts/%1/panels/%2/thumbnail").arg(id).arg(dindex)}}, 201);
                return;
            }
            if (sub == "thumbnail" && method == "GET") {
                QString projectDir = QFileInfo(m_projectPath).absolutePath();
                QString p = projectDir + "/.bridge/thumbs/" + id + ".png";
                if (!QFile::exists(p)) {
                    // 兜底：从 cut 的画面文件即时生成缩略图
                    QJsonArray ds = cut.value("drawings").toArray();
                    if (!ds.isEmpty()) {
                        QString lv = ds[0].toObject().value("level").toString();
                        QString src = QFileInfo(lv).isAbsolute() ? lv : (projectDir + "/" + lv);
                        QImage img;
                        if (!lv.isEmpty() && img.load(src)) {
                            QDir().mkpath(projectDir + "/.bridge/thumbs");
                            QImage th = img.scaled(640, 640, Qt::KeepAspectRatio, Qt::SmoothTransformation);
                            th.save(p, "PNG");
                        }
                    }
                }
                QFile f(p);
                if (!f.exists()) { sendError(s, 404, "NOT_FOUND", "缩略图不存在"); return; }
                f.open(QIODevice::ReadOnly);
                QByteArray data = f.readAll();
                QByteArray resp = "HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: " +
                                  QByteArray::number(data.size()) +
                                  "\r\nCache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n" + data;
                s->write(resp); s->disconnectFromHost(); return;
            }
            if (sub == "lock" && method == "POST") {
                QJsonObject cur = cut.value("lock").toObject();
                bool free = cur.isEmpty();
                if (!free) {
                    qint64 at = QDateTime::fromString(cur.value("at").toString(), Qt::ISODate).toMSecsSinceEpoch();
                    int ttl = cur.value("ttl").toInt();
                    if (ttl > 0 && nowMs() - at > qint64(ttl) * 1000) free = true;
                    if (!free && cur.value("byDevice").toString() != deviceId) {
                        sendError(s, 409, "LOCKED", "cut 已被锁定"); return;
                    }
                }
                int ttl = jbody.value("ttl").toInt(120);
                cut["lock"] = QJsonObject{{"byDevice", deviceId}, {"at", nowIso()}, {"ttl", ttl}};
                replaceCut(doc, idx, cut); saveDoc(doc);
                broadcast(QJsonObject{{"event", "takeover"}, {"cutId", id}, {"byDevice", deviceId}, {"ttl", ttl}});
                sendJson(s, QJsonObject{{"locked", true}, {"byDevice", deviceId}, {"ttl", ttl}}); return;
            }
            if (sub == "lock" && method == "DELETE") {
                cut["lock"] = QJsonValue();
                replaceCut(doc, idx, cut); saveDoc(doc);
                sendJson(s, QJsonObject{{"locked", false}}); return;
            }
            if (sub.isEmpty() && method == "DELETE") {
                QJsonArray arr = doc.value("cuts").toArray();
                QJsonArray out;
                for (int i = 0; i < arr.size(); ++i)
                    if (i != idx) out.append(arr[i]);
                doc["cuts"] = out;
                QJsonObject meta = doc.value("meta").toObject();
                meta["updatedAt"] = nowIso();
                doc["meta"] = meta;
                saveDoc(doc);
                broadcast(QJsonObject{{"event", "cutDeleted"}, {"cutId", id}});
                sendJson(s, QJsonObject{{"deleted", id}, {"remaining", out.size()}});
                return;
            }
            if (sub.isEmpty() && method == "PUT") {
                int expected = jbody.value("expectedRevision").toInt(-1);
                if (expected >= 0 && expected != cut.value("revision").toInt()) {
                    sendError(s, 409, "REVISION_CONFLICT", "revision 冲突"); return;
                }
                static const QSet<QString> allowed = {"action", "dialogue", "musicSe", "duration",
                                                     "frame", "camera", "state", "sequenceId"};
                for (auto it = jbody.begin(); it != jbody.end(); ++it) {
                    if (it.key() == "expectedRevision") continue;
                    if (!allowed.contains(it.key())) { sendError(s, 400, "BAD_FIELD", "字段不可改: " + it.key()); return; }
                    cut[it.key()] = it.value();
                }
                int rev = cut.value("revision").toInt() + 1;
                cut["revision"] = rev;
                cut["updatedAt"] = nowIso();
                replaceCut(doc, idx, cut);
                QJsonObject meta = doc.value("meta").toObject();
                meta["updatedAt"] = nowIso();
                doc["meta"] = meta;
                saveDoc(doc);
                broadcast(QJsonObject{{"event", "cutUpdated"}, {"cutId", id}, {"revision", rev}});
                sendJson(s, QJsonObject{{"revision", rev}}); return;
            }
            sendError(s, 501, "NOT_IMPLEMENTED", "该操作在 Qt Bridge 未实现（请用 Python Bridge）"); return;
        }

        if (path == "/api/export" && method == "POST") {
            QString jobId = "job-" + QUuid::createUuid().toString(QUuid::WithoutBraces).left(10);
            QJsonObject job{{"status", "queued"}, {"progress", 0.0}, {"outputs", QJsonArray()},
                            {"error", QJsonValue()}, {"createdAt", double(nowMs())}};
            m_jobs[jobId] = job;
            QString outDir = QFileInfo(m_projectPath).absolutePath() + "/deliverable/" + m_projectTitle;
            auto *proc = new QProcess(this);
            if (!m_pocPath.isEmpty()) {
                QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
                QString pp = env.value("PYTHONPATH");
                env.insert("PYTHONPATH", m_pocPath + (pp.isEmpty() ? "" : ";" + pp));
                proc->setProcessEnvironment(env);
            }
            connect(proc, &QProcess::started, this, [this, jobId]() {
                QJsonObject j = m_jobs.value(jobId);
                j["status"] = "running"; j["progress"] = 0.1; m_jobs[jobId] = j;
                broadcast(QJsonObject{{"event", "exportProgress"}, {"jobId", jobId}, {"status", "running"}, {"progress", 0.1}});
            });
            connect(proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished), this,
                    [this, jobId, proc, outDir](int code, QProcess::ExitStatus) {
                QJsonObject j = m_jobs.value(jobId);
                if (code == 0) {
                    j["status"] = "done"; j["progress"] = 1.0;
                    QJsonArray outs; outs.append(outDir + "/storyboard.pdf"); outs.append(outDir + "/manifest.json");
                    j["outputs"] = outs;
                } else {
                    j["status"] = "failed"; j["error"] = QString::fromUtf8(proc->readAllStandardError());
                }
                j["endedAt"] = double(nowMs());
                m_jobs[jobId] = j;
                broadcast(QJsonObject{{"event", "exportProgress"}, {"jobId", jobId},
                                      {"status", j["status"]}, {"progress", j["progress"]}});
                proc->deleteLater();
            });
            proc->setProgram(m_py);
            proc->setArguments({"-m", "konte_poc", "export", m_projectPath, "--out", outDir});
            proc->start();
            sendJson(s, QJsonObject{{"jobId", jobId}}, 202); return;
        }
        if (seg.size() == 3 && seg[0] == "api" && seg[1] == "export" && method == "GET") {
            QString jobId = seg[2];
            if (!m_jobs.contains(jobId)) { sendError(s, 404, "NOT_FOUND", "job 不存在"); return; }
            sendJson(s, m_jobs.value(jobId)); return;
        }

        sendError(s, 404, "NOT_FOUND", "no route");
    }

    // ---------------- WebSocket ----------------
    void doWs(QTcpSocket *s, const QMap<QString, QByteArray> &headers) {
        QByteArray key = headers.value("sec-websocket-key");
        if (key.isEmpty()) { sendError(s, 400, "BAD_WS", "缺少 Sec-WebSocket-Key"); return; }
        QByteArray resp = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                          "Connection: Upgrade\r\nSec-WebSocket-Accept: " +
                          wsAccept(key).toUtf8() + "\r\n\r\n";
        s->write(resp);
        s->setProperty("ws", true);
        m_ws.append(s);
        s->write(wsFrame(0x1, QByteArray("{\"event\":\"hello\",\"message\":\"konte bridge qt ws connected\"}")));
    }
    void broadcast(const QJsonObject &o) {
        QByteArray payload = QJsonDocument(o).toJson(QJsonDocument::Compact);
        QByteArray frame = wsFrame(0x1, payload);
        for (auto *s : m_ws) if (s->state() == QAbstractSocket::ConnectedState) s->write(frame);
    }

    QString m_projectPath, m_pin, m_py, m_pocPath, m_projectTitle;
    qint64 m_started = 0;
    qint64 m_tokenTtlMs = 12LL * 3600 * 1000;
    int m_maxPairFail = 5;
    qint64 m_pairWindowMs = 60 * 1000;
    QHash<QString, QJsonObject> m_tokens;
    QHash<QString, QJsonObject> m_jobs;
    QHash<QString, QList<qint64>> m_pairFails;
    QList<QTcpSocket *> m_ws;
};

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    QCoreApplication::setApplicationName("konte-bridge-qt");
    QString pluginPath = qEnvironmentVariable("QT_PLUGIN_PATH");
    if (!pluginPath.isEmpty()) QCoreApplication::addLibraryPath(pluginPath);
    QCommandLineParser parser;
    parser.addHelpOption();
    QCommandLineOption optProject(QStringList() << "p" << "project", "konte.json 路径", "path");
    QCommandLineOption optHost(QStringList() << "H" << "host", "监听地址", "host", "127.0.0.1");
    QCommandLineOption optPort(QStringList() << "P" << "port", "端口", "port", "17890");
    QCommandLineOption optPin(QStringList() << "pin", "配对 PIN", "pin", "");
    QCommandLineOption optPy(QStringList() << "py", "Python 可执行文件（导出用）", "path",
                             qEnvironmentVariable("KONTE_PY", "python"));
    QCommandLineOption optPoc(QStringList() << "poc", "konte_poc 所在目录（PYTHONPATH）", "path",
                              qEnvironmentVariable("KONTE_POC_PATH", ""));
    parser.addOptions({optProject, optHost, optPort, optPin, optPy, optPoc});
    parser.process(app);
    if (!parser.isSet(optProject)) { qCritical("缺少 --project"); return 2; }

    QString projectPath = QFileInfo(parser.value(optProject)).absoluteFilePath();
    QJsonObject doc;
    { QFile f(projectPath); if (!f.open(QIODevice::ReadOnly)) { qCritical("无法读取项目: %s", qPrintable(projectPath)); return 2; }
      doc = QJsonDocument::fromJson(f.readAll()).object(); }
    QString title = doc.value("project").toObject().value("title").toString("project");
    QString pin = parser.value(optPin);
    if (pin.isEmpty()) pin = QString::asprintf("%06d", QRandomGenerator::global()->bounded(1000000));

    BridgeServer server(projectPath, pin, parser.value(optPy), parser.value(optPoc));
    server.setProjectTitle(title);
    if (!server.listen(QHostAddress(parser.value(optHost)), quint16(parser.value(optPort).toUInt()))) {
        qCritical("监听失败: %s", qPrintable(server.errorString())); return 3;
    }
    printf("[konte-bridge-qt] listening http://%s:%u  PIN=%s\n",
           qPrintable(parser.value(optHost)), unsigned(parser.value(optPort).toUInt()), qPrintable(pin));
    fflush(stdout);
    return app.exec();
}
