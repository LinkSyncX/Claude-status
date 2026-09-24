"""在本工具中登录 Claude 账号：与 Claude Code ``/login`` 相同的 OAuth 流程。

以下细节取自 Claude Code 2.1.280 官方客户端：

1. 生成 PKCE（S256）与 ``state``，在 ``127.0.0.1`` 的随机端口启动一次性的
   回调服务；
2. 用浏览器打开 ``claude.com/cai/oauth/authorize``，``redirect_uri`` 为
   ``http://localhost:<端口>/callback``；收到回调后校验 ``state``，并把浏览器
   重定向到官方的登录成功页。浏览器无法回到本机（例如在另一台设备上登录）
   时，可以改用官方的手动回调页，把页面上显示的授权码粘贴回来；
3. 用授权码向 ``platform.claude.com/v1/oauth/token`` 换取令牌（JSON 请求体），
   再读取 ``/api/oauth/profile`` 得到邮箱、组织与套餐；
4. 整理成与 ``~/.claude/.credentials.json`` / ``~/.claude.json`` 相同结构的
   ``CodeLogin``。

登录在浏览器中完成，本工具只收到一次性的授权码，不接触账号密码。
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import http.server
import json
import secrets
import threading
import time
from typing import Any
import urllib.parse
import urllib.request

from claude_status import code_config
from claude_status import quota

CLIENT_ID = quota.CLIENT_ID
TOKEN_URL = quota.TOKEN_URL
AUTHORIZE_URL = "https://claude.com/cai/oauth/authorize"
PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"
MANUAL_REDIRECT_URL = "https://platform.claude.com/oauth/code/callback"
SUCCESS_URL = "https://platform.claude.com/oauth/code/success?app=claude-code"
# Claude Code 用订阅账号登录时申请的权限（kCr()）。
SCOPES = (
    "org:create_api_key",
    "user:profile",
    "user:inference",
    "user:sessions:claude_code",
    "user:mcp_servers",
    "user:file_upload",
    "user:plugins",
)
SUBSCRIPTIONS = {
    "claude_max": "max",
    "claude_pro": "pro",
    "claude_enterprise": "enterprise",
    "claude_team": "team",
}
CALLBACK_PATH = "/callback"


class LoginError(Exception):
    """登录失败（消息可直接展示给用户）。"""


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@dataclasses.dataclass(frozen=True)
class Pkce:
    """一次登录的 PKCE 参数与 ``state``。"""

    verifier: str
    challenge: str
    state: str

    @classmethod
    def create(cls) -> Pkce:
        """随机生成。"""
        verifier = _b64url(secrets.token_bytes(32))
        return cls(verifier, challenge_for(verifier), _b64url(secrets.token_bytes(32)))


def challenge_for(verifier: str) -> str:
    """S256 的 ``code_challenge``。"""
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def local_redirect_uri(port: int) -> str:
    """本机回调地址（与 Claude Code 一致使用 localhost）。"""
    return f"http://localhost:{port}{CALLBACK_PATH}"


def authorize_url(pkce: Pkce, redirect_uri: str, login_hint: str = "") -> str:
    """浏览器中打开的授权页地址。"""
    params = [
        ("code", "true"),
        ("client_id", CLIENT_ID),
        ("response_type", "code"),
        ("redirect_uri", redirect_uri),
        ("scope", " ".join(SCOPES)),
        ("code_challenge", pkce.challenge),
        ("code_challenge_method", "S256"),
        ("state", pkce.state),
    ]
    if login_hint:
        params.append(("login_hint", login_hint))
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def parse_manual_code(text: str, state: str) -> str:
    """解析手动回调页上的授权码：``code#state``、完整地址或单独的授权码。

    Raises:
        LoginError: 为空，或其中的 ``state`` 与本次登录不符。
    """
    text = text.strip()
    if not text:
        raise LoginError("请粘贴授权码")
    got_state = ""
    if "://" in text:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(text).query)
        code = (query.get("code") or [""])[0]
        got_state = (query.get("state") or [""])[0]
    else:
        code, _, got_state = text.partition("#")
    if not code:
        raise LoginError("没有找到授权码")
    if got_state and got_state != state:
        raise LoginError("授权码不属于本次登录，请重新登录")
    return code.strip()


# ---- 本机回调服务 ---------------------------------------------------------


class CallbackServer:
    """一次性的本机回调服务（只监听 127.0.0.1）。

    收到 ``state`` 正确的回调后记录授权码，并把浏览器重定向到官方的登录
    成功页；其他路径返回 404，``state`` 不符或授权被拒绝时返回说明页。
    """

    def __init__(self, state: str) -> None:
        self._state = state
        self._event = threading.Event()
        self.code = ""
        self.error = ""
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                server._handle(self)

            def log_message(self, *_args) -> None:
                pass  # 不在控制台打印请求（其中含授权码）

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="claude-login", daemon=True
        )

    @property
    def port(self) -> int:
        """监听的端口。"""
        return self._httpd.server_address[1]

    @property
    def done(self) -> bool:
        """是否已收到结果（授权码或错误）。"""
        return self._event.is_set()

    def start(self) -> None:
        """开始监听。"""
        self._thread.start()

    def stop(self) -> None:
        """停止监听。"""
        self._httpd.shutdown()
        self._httpd.server_close()

    def wait(self, timeout: float) -> bool:
        """等待结果，返回是否收到。"""
        return self._event.wait(timeout)

    def _handle(self, request: http.server.BaseHTTPRequestHandler) -> None:
        parts = urllib.parse.urlsplit(request.path)
        if parts.path != CALLBACK_PATH:
            request.send_error(404)
            return
        query = urllib.parse.parse_qs(parts.query)
        error = (query.get("error") or [""])[0]
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        if self._event.is_set():
            self._page(request, 409, "这次登录已经完成，可以关闭此页面。")
        elif error:
            detail = (query.get("error_description") or [error])[0]
            self.error = f"授权被拒绝：{detail}"
            self._page(request, 400, "登录没有完成，可以关闭此页面后重试。")
            self._event.set()
        elif state != self._state:
            # 可能是伪造的请求（CSRF），不结束本次登录。
            self._page(request, 400, "登录请求不匹配，请回到 Claude Status 重新登录。")
        elif not code:
            self._page(request, 400, "没有收到授权码，请重试。")
        else:
            self.code = code
            request.send_response(302)
            request.send_header("Location", SUCCESS_URL)
            request.end_headers()
            self._event.set()

    @staticmethod
    def _page(
        request: http.server.BaseHTTPRequestHandler, status: int, message: str
    ) -> None:
        body = (
            "<!doctype html><meta charset='utf-8'><title>Claude Status</title>"
            f"<p style='font:16px sans-serif;margin:40px'>{message}</p>"
        ).encode("utf-8")
        request.send_response(status)
        request.send_header("Content-Type", "text/html; charset=utf-8")
        request.send_header("Content-Length", str(len(body)))
        request.end_headers()
        request.wfile.write(body)


# ---- 换取令牌与账号资料 ---------------------------------------------------


def _post_json(opener: quota.Opener, url: str, body: dict[str, Any]) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": quota.user_agent()},
    )
    return quota.request_json(opener, request)


def exchange_code(
    code: str, pkce: Pkce, redirect_uri: str, opener: quota.Opener
) -> dict[str, Any]:
    """用授权码换取令牌。

    Raises:
        LoginError: 授权码无效、过期或网络错误。
    """
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": CLIENT_ID,
        "code_verifier": pkce.verifier,
        "state": pkce.state,
    }
    try:
        tokens = _post_json(opener, TOKEN_URL, body)
    except quota.QuotaError as exc:
        if exc.kind in ("auth", "http"):
            raise LoginError("授权码无效或已过期，请重新登录") from exc
        raise LoginError(str(exc)) from exc
    if not isinstance(tokens.get("access_token"), str):
        raise LoginError("登录服务没有返回访问令牌")
    return tokens


def fetch_profile(access_token: str, opener: quota.Opener) -> dict[str, Any]:
    """读取账号资料；失败时返回空字典（令牌本身仍然可用）。"""
    request = urllib.request.Request(
        PROFILE_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": quota.user_agent(),
        },
    )
    try:
        return quota.request_json(opener, request)
    except quota.QuotaError:
        return {}


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def build_login(
    tokens: dict[str, Any],
    profile: dict[str, Any],
    now: float | None = None,
) -> code_config.CodeLogin:
    """把令牌响应与账号资料整理成 Claude Code 的登录结构。"""
    now = time.time() if now is None else now
    account = _section(profile, "account")
    organization = _section(profile, "organization")
    # 读取资料失败时，令牌响应里也带有账号与组织的基本信息。
    token_account = _section(tokens, "account")
    token_org = _section(tokens, "organization")
    scope = tokens.get("scope")
    scopes = scope.split() if isinstance(scope, str) and scope else list(SCOPES)
    oauth: dict[str, Any] = {
        "accessToken": tokens["access_token"],
        "refreshToken": tokens.get("refresh_token") or "",
        "expiresAt": None,
        "scopes": scopes,
        "subscriptionType": SUBSCRIPTIONS.get(
            str(organization.get("organization_type") or "")
        ),
        "rateLimitTier": organization.get("rate_limit_tier"),
    }
    expires_in = tokens.get("expires_in")
    if isinstance(expires_in, int | float):
        oauth["expiresAt"] = int((now + expires_in) * 1000)
    oauth_account = {
        "accountUuid": account.get("uuid") or token_account.get("uuid"),
        "emailAddress": account.get("email") or token_account.get("email_address"),
        "organizationUuid": organization.get("uuid") or token_org.get("uuid"),
        "organizationName": organization.get("name") or token_org.get("name"),
        "displayName": account.get("display_name"),
        "fullName": account.get("full_name"),
        "billingType": organization.get("billing_type"),
    }
    oauth_account = {k: v for k, v in oauth_account.items() if v not in (None, "")}
    return code_config.CodeLogin({code_config.OAUTH_KEY: oauth}, oauth_account)


def complete_login(
    code: str, pkce: Pkce, redirect_uri: str, proxy: str = ""
) -> code_config.CodeLogin:
    """（工作线程）换取令牌并读取账号资料。

    Raises:
        LoginError: 换取令牌失败。
    """
    opener = quota.make_opener(proxy)
    tokens = exchange_code(code, pkce, redirect_uri, opener)
    profile = fetch_profile(tokens["access_token"], opener)
    return build_login(tokens, profile)
