# SPDX-License-Identifier: BSD-3-Clause
"""统一的错误类型。Bridge 会把它们映射为 HTTP 状态码（422/409/400）。"""


class KonteError(Exception):
    """所有 konte 相关错误的基类。"""


class SchemaError(KonteError):
    """konte.json 不符合 JSON Schema。"""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(str(e) for e in self.errors) or "schema validation failed")


class InvariantError(KonteError):
    """不符合业务不变量（时长换算、至少一张画面等）。"""


class ExportGateError(KonteError):
    """决定稿闸门未通过（未锁定 / 存在 TBD 时长）。"""

    def __init__(self, message, details=None):
        self.details = details or []
        super().__init__(message)
