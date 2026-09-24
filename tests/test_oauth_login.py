"""在本工具中登录（OAuth）的测试：不访问任何真实的登录服务。"""

import http.client
import io
import json
import sys
import time
import unittest
import urllib.error
import urllib.parse
from unittest import mock

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

import md3

from claude_status import app as app_module
from claude_status import code_config
from claude_status import models
from claude_status import oauth_login
from claude_status import quota
from claude_status import state as state_module
from claude_status import storage
from claude_status import switcher
from claude_status.pages import login_dialog
from tests import fixtures
from tests import qt

_APP = qt.application()

TOKENS = {
    "access_token": "sk-ant-oat01-new",
    "refresh_token": "sk-ant-ort01-new",
    "expires_in": 28800,
    "scope": "user:profile user:inference user:sessions:claude_code",
    "token_type": "Bearer",
    "account": {"uuid": "uuid-new", "email_address": "new@example.com"},
    "organization": {"uuid": "org-new", "name": "New Org"},
}
PROFILE = {
    "account": {
        "uuid": "uuid-new",
        "email": "new@example.com",
        "display_name": "New User",
        "full_name": "New Full",
    },
    "organization": {
        "uuid": "org-new",
        "name": "New Org",
        "organization_type": "claude_max",
        "rate_limit_tier": "default_claude_max_20x",
        "billing_type": "stripe_subscription",
    },
}


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


class FakeOpener:
    """记录请求并按地址返回预设 JSON（或 HTTP 错误）。"""

    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def __call__(self, request, _timeout):
        self.requests.append(request)
        result = self.responses[request.full_url]
        if isinstance(result, int):
            raise urllib.error.HTTPError(
                request.full_url, result, "error", {}, io.BytesIO(b"{}")
            )
        return _Response(json.dumps(result).encode("utf-8"))


def _pump_until(predicate, timeout_ms: int = 5000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if predicate():
            return True
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(20, loop.quit)
        loop.exec()
    return predicate()


def _get(port: int, path: str) -> http.client.HTTPResponse:
    """访问本机回调服务（http.client 不会跟随重定向）。"""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    response.read()
    connection.close()
    return response


class OAuthFlowTest(unittest.TestCase):
    def test_pkce_matches_rfc7636(self):
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        self.assertEqual(
            oauth_login.challenge_for(verifier),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        )
        pkce = oauth_login.Pkce.create()
        self.assertEqual(pkce.challenge, oauth_login.challenge_for(pkce.verifier))
        self.assertGreaterEqual(len(pkce.verifier), 43)

    def test_authorize_url_matches_claude_code(self):
        pkce = oauth_login.Pkce("v", "c", "s")
        url = oauth_login.authorize_url(
            pkce, oauth_login.local_redirect_uri(54545), "me@example.com"
        )
        parts = urllib.parse.urlsplit(url)
        self.assertEqual(
            f"{parts.scheme}://{parts.netloc}{parts.path}",
            "https://claude.com/cai/oauth/authorize",
        )
        query = dict(urllib.parse.parse_qsl(parts.query))
        self.assertEqual(
            query,
            {
                "code": "true",
                "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
                "response_type": "code",
                "redirect_uri": "http://localhost:54545/callback",
                "scope": " ".join(oauth_login.SCOPES),
                "code_challenge": "c",
                "code_challenge_method": "S256",
                "state": "s",
                "login_hint": "me@example.com",
            },
        )

    def test_callback_server(self):
        server = oauth_login.CallbackServer("expected")
        server.start()
        self.addCleanup(server.stop)
        self.assertEqual(_get(server.port, "/other").status, 404)
        # state 不符：拒绝，但继续等待正确的回调。
        self.assertEqual(_get(server.port, "/callback?code=x&state=bad").status, 400)
        self.assertFalse(server.done)
        response = _get(server.port, "/callback?code=abc&state=expected")
        self.assertEqual(response.status, 302)
        self.assertEqual(response.getheader("Location"), oauth_login.SUCCESS_URL)
        self.assertTrue(server.wait(1))
        self.assertEqual((server.code, server.error), ("abc", ""))

    def test_callback_server_reports_denial(self):
        server = oauth_login.CallbackServer("s")
        server.start()
        self.addCleanup(server.stop)
        path = "/callback?error=access_denied&error_description=denied&state=s"
        self.assertEqual(_get(server.port, path).status, 400)
        self.assertTrue(server.done)
        self.assertIn("denied", server.error)

    def test_parse_manual_code(self):
        self.assertEqual(oauth_login.parse_manual_code(" abc#s ", "s"), "abc")
        self.assertEqual(oauth_login.parse_manual_code("abc", "s"), "abc")
        url = f"{oauth_login.MANUAL_REDIRECT_URL}?code=abc&state=s"
        self.assertEqual(oauth_login.parse_manual_code(url, "s"), "abc")
        for bad in ("", "abc#other", "#s"):
            with self.subTest(text=bad):
                with self.assertRaises(oauth_login.LoginError):
                    oauth_login.parse_manual_code(bad, "s")

    def test_exchange_and_build_login(self):
        opener = FakeOpener(
            {oauth_login.TOKEN_URL: TOKENS, oauth_login.PROFILE_URL: PROFILE}
        )
        pkce = oauth_login.Pkce("verifier", "challenge", "state")
        redirect = oauth_login.local_redirect_uri(1234)
        tokens = oauth_login.exchange_code("code-1", pkce, redirect, opener)
        [request] = opener.requests
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            json.loads(request.data),
            {
                "grant_type": "authorization_code",
                "code": "code-1",
                "redirect_uri": redirect,
                "client_id": oauth_login.CLIENT_ID,
                "code_verifier": "verifier",
                "state": "state",
            },
        )
        profile = oauth_login.fetch_profile(tokens["access_token"], opener)
        self.assertEqual(
            opener.requests[1].get_header("Authorization"),
            "Bearer sk-ant-oat01-new",
        )
        login = oauth_login.build_login(tokens, profile, now=1000.0)
        oauth = login.oauth
        self.assertEqual(oauth["accessToken"], "sk-ant-oat01-new")
        self.assertEqual(oauth["refreshToken"], "sk-ant-ort01-new")
        self.assertEqual(oauth["expiresAt"], (1000 + 28800) * 1000)
        self.assertEqual(oauth["subscriptionType"], "max")
        self.assertEqual(oauth["rateLimitTier"], "default_claude_max_20x")
        self.assertEqual(oauth["scopes"], TOKENS["scope"].split())
        self.assertEqual(
            login.oauth_account,
            {
                "accountUuid": "uuid-new",
                "emailAddress": "new@example.com",
                "organizationUuid": "org-new",
                "organizationName": "New Org",
                "displayName": "New User",
                "fullName": "New Full",
                "billingType": "stripe_subscription",
            },
        )

    def test_profile_failure_falls_back_to_token_response(self):
        opener = FakeOpener({oauth_login.PROFILE_URL: 500})
        self.assertEqual(oauth_login.fetch_profile("token", opener), {})
        login = oauth_login.build_login(TOKENS, {}, now=0)
        self.assertEqual(login.email, "new@example.com")
        self.assertEqual(login.org_uuid, "org-new")
        self.assertIsNone(login.oauth["subscriptionType"])

    def test_invalid_code_is_reported(self):
        opener = FakeOpener({oauth_login.TOKEN_URL: 400})
        pkce = oauth_login.Pkce("v", "c", "s")
        with self.assertRaises(oauth_login.LoginError) as caught:
            oauth_login.exchange_code("bad", pkce, "r", opener)
        self.assertIn("授权码", str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, quota.QuotaError)


def _login(name: str) -> code_config.CodeLogin:
    return oauth_login.build_login(
        {
            **TOKENS,
            "access_token": f"access-{name}",
            "refresh_token": f"refresh-{name}",
        },
        {
            "account": {"uuid": f"uuid-{name}", "email": f"{name}@example.com"},
            "organization": {
                "uuid": f"org-{name}",
                "organization_type": "claude_max",
                "rate_limit_tier": "default_claude_max_20x",
            },
        },
    )


class LoginUiTest(fixtures.IsolatedClaudeTest):
    def setUp(self):
        super().setUp()
        self.errors: list[BaseException] = []
        previous_hook = sys.excepthook
        sys.excepthook = lambda _type, value, _tb: self.errors.append(value)
        self.addCleanup(setattr, sys, "excepthook", previous_hook)
        self.state = state_module.AppState(
            storage.Store(self.data_dir), offline=True
        )
        self.addCleanup(self.state.shutdown)
        md3.install(
            _APP,
            seed=self.state.settings.seed,
            extended=app_module.EXTENDED_COLORS,
            locale="zh",
        )
        self.opened: list[str] = []
        patcher = mock.patch.object(
            QtGui.QDesktopServices,
            "openUrl",
            side_effect=lambda url: self.opened.append(url.toString()),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.assertEqual(self.errors, [], "槽函数中出现异常")

    def test_add_login_creates_and_updates_accounts(self):
        clients = self.state.clients
        account, created = clients.add_login(_login("carol"))
        self.assertTrue(created)
        self.assertEqual(
            (account.email, account.claude_uuid, account.org_uuid),
            ("carol@example.com", "uuid-carol", "org-carol"),
        )
        self.assertIs(account.plan, models.Plan.MAX_20X)
        self.assertTrue(clients.vault.has_code(account.id))
        # 再次登录同一账号：更新而不是新建。
        again, created = clients.add_login(_login("carol"))
        self.assertIs(again, account)
        self.assertFalse(created)
        with self.assertRaises(switcher.SwitchError):
            clients.add_login(_login("dave"), target=account)

    def _dialog(self, target=None):
        dialog = login_dialog.LoginDialog(self.state, target)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.addCleanup(dialog.deleteLater)
        dialog.show()
        self.assertTrue(_pump_until(lambda: bool(self.opened)))
        return dialog

    def test_dialog_completes_after_browser_callback(self):
        with mock.patch.object(
            oauth_login, "complete_login", return_value=_login("erin")
        ) as complete:
            dialog = self._dialog()
            query = dict(
                urllib.parse.parse_qsl(urllib.parse.urlsplit(self.opened[-1]).query)
            )
            redirect = urllib.parse.urlsplit(query["redirect_uri"])
            response = _get(
                redirect.port, f"/callback?code=cb-code&state={query['state']}"
            )
            self.assertEqual(response.status, 302)
            self.assertTrue(_pump_until(lambda: dialog.result() != 0))
        self.assertEqual(dialog.result(), QtWidgets.QDialog.DialogCode.Accepted)
        code, pkce, redirect_uri, _proxy = complete.call_args.args
        self.assertEqual(code, "cb-code")
        self.assertEqual(pkce.state, query["state"])
        self.assertEqual(redirect_uri, query["redirect_uri"])
        self.assertEqual(dialog.account.email, "erin@example.com")
        self.assertTrue(self.state.clients.vault.has_code(dialog.account.id))

    def test_dialog_manual_code(self):
        with mock.patch.object(
            oauth_login, "complete_login", return_value=_login("finn")
        ) as complete:
            dialog = self._dialog()
            dialog._use_manual()  # noqa: SLF001
            self.assertTrue(
                _pump_until(
                    lambda: oauth_login.MANUAL_REDIRECT_URL
                    in urllib.parse.unquote(self.opened[-1])
                )
            )
            state = dict(
                urllib.parse.parse_qsl(urllib.parse.urlsplit(self.opened[-1]).query)
            )["state"]
            dialog._code.set_text(f"manual-code#{state}")  # noqa: SLF001
            dialog._submit_code()  # noqa: SLF001
            self.assertTrue(_pump_until(lambda: dialog.result() != 0))
        code, _pkce, redirect_uri, _proxy = complete.call_args.args
        self.assertEqual(
            (code, redirect_uri), ("manual-code", oauth_login.MANUAL_REDIRECT_URL)
        )
        self.assertEqual(dialog.account.email, "finn@example.com")


if __name__ == "__main__":
    unittest.main()
