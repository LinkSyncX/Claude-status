"""本机加密：Windows 上使用 DPAPI，密文只能由当前 Windows 用户解密。

保存的登录凭据、API Key 与切换备份都经由这里加密后落盘；复制到其他
电脑或其他用户下无法解密。非 Windows 平台没有等价的系统接口，数据以
带标记的明文保存（界面会提示）。
"""

from __future__ import annotations

import base64
import ctypes
import sys

_DPAPI_PREFIX = b"DPAPI1:"
_PLAIN_PREFIX = b"PLAIN1:"
TEXT_PREFIX = "enc:v1:"
_DESCRIPTION = "claude-status"
_UI_FORBIDDEN = 0x01


class SecureError(Exception):
    """加密或解密失败（例如密文来自其他电脑或其他用户）。"""


def available() -> bool:
    """当前平台是否提供系统级加密（仅 Windows DPAPI）。"""
    return sys.platform == "win32"


def description() -> str:
    """界面上显示的加密状态，可直接接在主语后，如"保存的登录已使用…"。"""
    if available():
        return "已使用 Windows DPAPI 加密（仅当前 Windows 用户可以解密）"
    return "未加密（当前平台没有可用的系统加密接口）"


if sys.platform == "win32":
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_Blob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_Blob),
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_Blob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_Blob),
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p

    def _dpapi(data: bytes, protect: bool) -> bytes:
        buffer = ctypes.create_string_buffer(data, len(data))
        blob_in = _Blob(
            len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
        )
        blob_out = _Blob()
        if protect:
            ok = _crypt32.CryptProtectData(
                ctypes.byref(blob_in),
                _DESCRIPTION,
                None,
                None,
                None,
                _UI_FORBIDDEN,
                ctypes.byref(blob_out),
            )
        else:
            ok = _crypt32.CryptUnprotectData(
                ctypes.byref(blob_in),
                None,
                None,
                None,
                None,
                _UI_FORBIDDEN,
                ctypes.byref(blob_out),
            )
        if not ok:
            code = ctypes.get_last_error()
            action = "加密" if protect else "解密"
            raise SecureError(f"DPAPI {action}失败（错误码 {code}）")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            _kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def protect(data: bytes) -> bytes:
    """加密字节串，结果带格式前缀。"""
    if available():
        return _DPAPI_PREFIX + _dpapi(data, protect=True)
    return _PLAIN_PREFIX + data


def unprotect(data: bytes) -> bytes:
    """解密 ``protect`` 的结果。

    Raises:
        SecureError: 格式无法识别或解密失败。
    """
    if data.startswith(_DPAPI_PREFIX):
        if not available():
            raise SecureError("该数据由 Windows DPAPI 加密，只能在原电脑上解密")
        return _dpapi(data[len(_DPAPI_PREFIX) :], protect=False)
    if data.startswith(_PLAIN_PREFIX):
        return data[len(_PLAIN_PREFIX) :]
    raise SecureError("无法识别的加密数据格式")


def protect_text(text: str) -> str:
    """加密字符串，结果为 ``enc:v1:<base64>``；空字符串原样返回。"""
    if not text:
        return ""
    payload = base64.b64encode(protect(text.encode("utf-8")))
    return TEXT_PREFIX + payload.decode("ascii")


def unprotect_text(value: str) -> str:
    """解密 ``protect_text`` 的结果；没有前缀的值视为旧版明文原样返回。

    Raises:
        SecureError: 解密失败。
    """
    if not value.startswith(TEXT_PREFIX):
        return value
    try:
        payload = base64.b64decode(value[len(TEXT_PREFIX) :], validate=True)
    except ValueError as exc:
        raise SecureError("加密文本已损坏") from exc
    return unprotect(payload).decode("utf-8")
