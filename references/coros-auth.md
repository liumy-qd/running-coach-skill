# COROS 跨平台授权

真实 COROS 凭证只保留在本机 `coros-mcp` 缓存中。不要把 token、OAuth state、poll token、授权链接或回调参数写入对话、日志或报告。

## 首选流程

当调用返回 `no local token cache found`、`run login first`、`invalid_grant`、`cli session expired`、`unauthorized` 或 `401` 时，在 Skill 根目录运行：

```bash
python3 scripts/coros_auth_bootstrap.py --mode auto
```

脚本先验证现有登录；需要重新授权时，根据 macOS、Windows、Linux、WSL、SSH/容器环境选择自动打开浏览器或手动模式。授权成功后再次验证 `queryRecoveryStatus()`，然后继续原数据请求。

## 诊断模式

```bash
python3 scripts/coros_auth_bootstrap.py --mode check --json
python3 scripts/coros_auth_bootstrap.py --mode manual-link --show-url
python3 scripts/coros_auth_bootstrap.py --mode finish-only
```

仅当自动打开失败、用户明确需要复制链接或正在排查 CLI 时才使用 `--show-url`。远程 agent 无法替用户完成浏览器确认时，只说明需要在浏览器确认授权，不回显凭证材料。

## 退出码

| 码 | 含义 | 下一步 |
|---|---|---|
| 0 | 已登录并验证通过 | 继续原任务 |
| 1 | 授权过期（`auth_required`）或验证失败（`error`） | `--mode auto` 重新授权 |
| 2 | 参数错误 | 检查命令行参数 |
| 3 | `manual_required`：无法自动打开浏览器 | 加 `--show-url` 让用户手动完成 |
| 4 | `missing_cli`：未找到 coros-mcp | 先安装 coros-mcp CLI |
