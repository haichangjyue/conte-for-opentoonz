# SPDX-License-Identifier: BSD-3-Clause
"""极简 WebSocket（RFC 6455）服务端：握手 + 文本帧广播。

只实现本产品需要的最小集：服务端 → 客户端的事件推送（cutUpdated/thumbnailReady/
exportProgress/takeover）。不做分片、压缩、二进制。零第三方依赖。
"""

from __future__ import annotations

import base64
import hashlib
import socket
import struct
import threading

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def accept_key(client_key: str) -> str:
    sha = hashlib.sha1((client_key + _GUID).encode("ascii")).digest()
    return base64.b64encode(sha).decode("ascii")


def handshake_response(headers) -> bytes | None:
    key = headers.get("Sec-WebSocket-Key")
    if not key:
        return None
    acc = accept_key(key)
    return (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {acc}\r\n\r\n"
    ).encode("ascii")


def encode_text(payload: str) -> bytes:
    data = payload.encode("utf-8")
    header = bytearray()
    header.append(0x81)  # FIN + text
    n = len(data)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    return bytes(header) + data


def _read_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def read_frame(sock: socket.socket) -> tuple[int, bytes]:
    b1 = _read_exact(sock, 1)[0]
    b2 = _read_exact(sock, 1)[0]
    opcode = b1 & 0x0F
    masked = b2 & 0x80
    ln = b2 & 0x7F
    if ln == 126:
        ln = struct.unpack(">H", _read_exact(sock, 2))[0]
    elif ln == 127:
        ln = struct.unpack(">Q", _read_exact(sock, 8))[0]
    mask = _read_exact(sock, 4) if masked else None
    data = _read_exact(sock, ln) if ln else b""
    if mask:
        data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
    return opcode, data


class Hub:
    """连接的 WebSocket 客户端集合，线程安全广播。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._clients: list[socket.socket] = []

    def add(self, sock: socket.socket):
        with self._lock:
            self._clients.append(sock)

    def remove(self, sock: socket.socket):
        with self._lock:
            if sock in self._clients:
                self._clients.remove(sock)

    def broadcast(self, text: str):
        frame = encode_text(text)
        dead = []
        with self._lock:
            for s in list(self._clients):
                try:
                    s.sendall(frame)
                except Exception:
                    dead.append(s)
            for s in dead:
                if s in self._clients:
                    self._clients.remove(s)

    def count(self) -> int:
        with self._lock:
            return len(self._clients)
