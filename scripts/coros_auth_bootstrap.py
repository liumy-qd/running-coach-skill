#!/usr/bin/env python3
"""Cross-platform COROS MCP login bootstrap with secret-safe output."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import webbrowser
from typing import Any


AUTH_ERRORS = ("no local token cache found", "run login first", "invalid_grant", "cli session expired", "unauthorized", "401")
URL_RE = re.compile(r"https://\S+")


def run(args: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def sanitized(value: str) -> str:
    value = URL_RE.sub("[授权链接已隐藏]", value.strip())
    return re.sub(r"(?i)(access|refresh|poll|id)[_-]?token[^\s,}]*", "[凭证已隐藏]", value)


def emit(status: str, message: str, code: int, json_mode: bool, extra: dict[str, Any] | None = None) -> int:
    payload = {"status": status, "message": message, "exit_code": code, **(extra or {})}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True) if json_mode else message)
    return code


def verify(cli: str) -> tuple[bool, str]:
    result = run([cli, "call-tool", "--tool", "queryRecoveryStatus", "--arguments-json", "{}"], 60)
    return result.returncode == 0, (result.stdout + "\n" + result.stderr).strip()


def environment() -> dict[str, Any]:
    system = platform.system() or "Unknown"
    is_wsl = bool(os.environ.get("WSL_DISTRO_NAME")) or "microsoft" in platform.release().lower()
    remote = bool(os.environ.get("SSH_CONNECTION") or os.environ.get("CI"))
    display = system in {"Darwin", "Windows"} or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return {"os": system, "is_wsl": is_wsl, "is_remote": remote, "is_headless": remote or not display}


def open_url(url: str, env: dict[str, Any]) -> bool:
    if env["is_headless"]:
        return False
    commands: list[list[str]] = []
    if env["os"] == "Darwin":
        commands = [["open", url]]
    elif env["is_wsl"]:
        commands = [["wslview", url], ["cmd.exe", "/c", "start", "", url]]
    elif env["os"] == "Linux":
        commands = [["xdg-open", url], ["gio", "open", url]]
    elif env["os"] == "Windows":
        commands = [["cmd", "/c", "start", "", url]]
    for command in commands:
        if shutil.which(command[0]) and run(command, 20).returncode == 0:
            return True
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def start_login(cli: str) -> str:
    status = run([cli, "login-status"], 30)
    if "pending login session found" in (status.stdout + status.stderr):
        run([cli, "logout"], 30)
    result = run([cli, "login-start"], 90)
    match = URL_RE.search(result.stdout + "\n" + result.stderr)
    if result.returncode != 0 or not match:
        raise RuntimeError(sanitized(result.stdout + "\n" + result.stderr) or "无法创建授权会话")
    return match.group(0)


def finish(cli: str, timeout: int) -> None:
    result = run([cli, "login-finish", "--timeout", str(timeout)], timeout + 30)
    if result.returncode != 0:
        raise RuntimeError(sanitized(result.stdout + "\n" + result.stderr) or "授权未完成")


def main() -> int:
    parser = argparse.ArgumentParser(description="引导 COROS MCP 跨平台授权并验证只读接口。")
    parser.add_argument("--mode", choices=("auto", "interactive", "manual-link", "finish-only", "check"), default="auto")
    parser.add_argument("--show-url", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--coros-mcp")
    args = parser.parse_args()
    cli = args.coros_mcp or shutil.which("coros-mcp")
    if not cli:
        return emit("missing_cli", "未找到 coros-mcp，请先安装 CLI。", 4, args.json)
    env = environment()
    ok, detail = verify(cli)
    if ok:
        return emit("ok", "COROS 已登录，数据接口验证通过。", 0, args.json, {"environment": env})
    if args.mode == "check":
        auth_required = any(item in detail.lower() for item in AUTH_ERRORS)
        return emit("auth_required" if auth_required else "error", "COROS 尚未登录或授权已过期。" if auth_required else f"验证失败：{sanitized(detail)}", 1, args.json, {"environment": env})
    try:
        if args.mode == "finish-only":
            finish(cli, args.timeout)
        else:
            url = start_login(cli)
            mode = "manual-link" if args.mode == "auto" and env["is_headless"] else args.mode
            opened = False if mode == "manual-link" else open_url(url, env)
            if opened:
                print("已打开 COROS 授权页面，请在浏览器确认授权。", file=sys.stderr if args.json else sys.stdout)
            elif args.show_url:
                print(url, file=sys.stderr if args.json else sys.stdout)
            else:
                return emit("manual_required", "无法自动打开浏览器。需要手动复制时重新运行并添加 --show-url。", 3, args.json, {"environment": env})
            finish(cli, args.timeout)
        ok, detail = verify(cli)
        if not ok:
            raise RuntimeError(sanitized(detail))
        return emit("ok", "COROS 授权完成，数据接口验证通过。", 0, args.json, {"environment": env})
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        return emit("error", f"COROS 授权失败：{sanitized(str(exc))}", 1, args.json, {"environment": env})


if __name__ == "__main__":
    raise SystemExit(main())
