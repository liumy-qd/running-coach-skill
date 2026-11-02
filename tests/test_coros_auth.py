#!/usr/bin/env python3
"""coros_auth_bootstrap.py 模拟测试：脱敏、环境判定、错误分类、退出码与登录流程。

全部 subprocess 调用以 fake 结果注入，不触网、不依赖真实 coros-mcp、不使用真凭证。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))


def load(name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = load("coros_auth_bootstrap")

AUTH_LINK = "https://mcp.coros.com/oauth/authorize?client_id=app&state=abc123"
LOOPBACK = "http://127.0.0.1:8931/callback?code=xyz&state=abc123"


class FakeResult:
    """subprocess.CompletedProcess 的最小替身（脚本只读 returncode/stdout/stderr）。"""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_cli(*argv: str, run_results=None, verify_results=None,
            env=None, system=None, which="fake-cli"):
    """在完整 stub 环境下执行 main()，返回 (exit_code, stdout 文本, open_url mock)。

    默认注入 --coros-mcp fake-cli，避免查询真实的 coros-mcp 安装状态；
    which=None 表示模拟 CLI 未安装（且不注入该参数，走真实 argparse 分支）。
    """
    if which is not None:
        argv = (*argv, "--coros-mcp", which)
    out, err = io.StringIO(), io.StringIO()
    opened = mock.Mock(return_value=True)
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(sys, "argv",
                                              ["coros_auth_bootstrap.py", *argv]))
        stack.enter_context(mock.patch.dict(os.environ, env or {}, clear=True))
        if system:
            stack.enter_context(mock.patch.object(auth.platform, "system",
                                                  return_value=system))
        if which is None:
            stack.enter_context(mock.patch.object(auth.shutil, "which",
                                                  return_value=None))
        if run_results is not None:
            stack.enter_context(mock.patch.object(auth, "run",
                                                  side_effect=run_results))
        if verify_results is not None:
            stack.enter_context(mock.patch.object(auth, "verify",
                                                  side_effect=verify_results))
        stack.enter_context(mock.patch.object(auth, "open_url", opened))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        code = auth.main()
    return code, out.getvalue(), opened


class TestSanitized(unittest.TestCase):
    def test_hides_https_auth_link(self):
        text = auth.sanitized(f"login at {AUTH_LINK} to continue")
        self.assertNotIn("https://", text)
        self.assertNotIn("state=abc123", text)
        self.assertIn("[授权链接已隐藏]", text)

    def test_hides_http_loopback_callback(self):
        text = auth.sanitized(f"redirect {LOOPBACK}")
        self.assertNotIn("127.0.0.1", text)
        self.assertNotIn("code=xyz", text)

    def test_hides_kv_tokens(self):
        text = auth.sanitized("access_token=aaa.bbb refresh_token=ccc poll_token=ddd id_token=eee")
        for secret in ("aaa.bbb", "ccc", "ddd", "eee"):
            self.assertNotIn(secret, text)
        self.assertEqual(text.count("[凭证已隐藏]"), 4)

    def test_hides_json_style_tokens(self):
        text = auth.sanitized('{"access_token": "eyJhbGci.eyJz.zFr", "token_type": "Bearer"}')
        self.assertNotIn("eyJhbGci", text)
        self.assertIn("token_type", text)  # 非凭证键名保留，便于排障

    def test_plain_message_survives(self):
        self.assertEqual(auth.sanitized("COROS 已登录\n"), "COROS 已登录")

    def test_separatorless_key_only_replaced(self):
        # 无 [:=] 分隔时不吞正文：只替换键名本身
        text = auth.sanitized("access_token is required for this action")
        self.assertNotIn("access_token", text)
        self.assertIn("is required", text)


class TestEnvironment(unittest.TestCase):
    def test_ci_env_is_headless(self):
        with mock.patch.dict(os.environ, {"CI": "1"}, clear=True):
            env = auth.environment()
        self.assertTrue(env["is_remote"])
        self.assertTrue(env["is_headless"])

    def test_desktop_darwin_not_headless(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(auth.platform, "system", return_value="Darwin"):
            env = auth.environment()
        self.assertFalse(env["is_remote"])
        self.assertFalse(env["is_headless"])


class TestCheckMode(unittest.TestCase):
    def check(self, detail: str):
        code, out, _ = run_cli("--mode", "check", "--json",
                               run_results=[FakeResult(1, "", detail)])
        return code, json.loads(out)

    def test_logged_in_passes_without_login(self):
        code, out, _ = run_cli("--mode", "check", "--json",
                               run_results=[FakeResult(0, "recovery ok")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], "ok")

    def test_every_auth_error_maps_to_auth_required(self):
        for detail in auth.AUTH_ERRORS:
            code, payload = self.check(detail)
            self.assertEqual(code, 1, detail)
            self.assertEqual(payload["status"], "auth_required", detail)

    def test_unknown_error_maps_to_error(self):
        code, payload = self.check("connection reset by peer")
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "error")


class TestLoginFlow(unittest.TestCase):
    def test_successful_flow_returns_ok(self):
        run_results = [
            FakeResult(0, ""),                        # login-status：无 pending 会话
            FakeResult(0, f"open {AUTH_LINK}"),       # login-start
            FakeResult(0, "done"),                    # login-finish
        ]
        code, out, opened = run_cli(
            "--mode", "auto", "--json",
            run_results=run_results,
            verify_results=[(False, "run login first"), (True, "ok")],
            env={"DISPLAY": ":0"}, system="Darwin",
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], "ok")
        opened.assert_called_once()

    def test_headless_auto_without_show_url_requires_manual(self):
        run_results = [
            FakeResult(0, ""),
            FakeResult(0, f"visit {AUTH_LINK}"),
        ]
        code, out, opened = run_cli(
            "--mode", "auto", "--json",
            run_results=run_results,
            verify_results=[(False, "run login first")],
            env={"CI": "1"},  # headless：无法自动打开浏览器
        )
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["status"], "manual_required")
        opened.assert_not_called()


class TestStartLogin(unittest.TestCase):
    def start(self, *results):
        with mock.patch.object(auth, "run", side_effect=list(results)):
            return auth.start_login("fake-cli")

    def test_extracts_first_url(self):
        url = self.start(FakeResult(0, ""),
                         FakeResult(0, "visit https://auth.coros.com/authorize?x=1 now"))
        self.assertEqual(url, "https://auth.coros.com/authorize?x=1")

    def test_failure_raises_sanitized(self):
        with self.assertRaises(RuntimeError) as cm:
            self.start(FakeResult(0, ""),
                       FakeResult(1, "", f"denied {AUTH_LINK} access_token=secret123"))
        message = str(cm.exception)
        self.assertNotIn("https://", message)
        self.assertNotIn("secret123", message)

    def test_no_url_raises(self):
        with self.assertRaises(RuntimeError):
            self.start(FakeResult(0, ""), FakeResult(0, "no link here"))

    def test_pending_session_logged_out_first(self):
        runs = [FakeResult(0, "pending login session found"),
                FakeResult(0, "logged out"),
                FakeResult(0, f"open {AUTH_LINK}")]
        url = self.start(*runs)
        self.assertEqual(url, AUTH_LINK)


class TestMissingCli(unittest.TestCase):
    def test_exit_4_when_cli_absent(self):
        code, out, _ = run_cli("--mode", "check", "--json", which=None)
        self.assertEqual(code, 4)
        self.assertEqual(json.loads(out)["status"], "missing_cli")


if __name__ == "__main__":
    unittest.main()
