# Privacy and Data Safety

This repository is designed to be safe for public use and contribution.

## Do Not Commit

Never commit:

- Watch-vendor access tokens or refresh tokens (COROS OAuth, Garmin/garth tokens).
- OAuth callback URLs or state parameters.
- Passwords, API keys, or secrets.
- Real health exports.
- Private activity files such as FIT, GPX, TCX, or screenshots with personal details.
- Location traces that reveal home, workplace, or private routes.
- Menstrual-cycle data or notes. This skill queries them only for an explicit user request and does not archive them by default.

## Use Synthetic Data

Examples in this repository are synthetic. When reporting issues, use synthetic, anonymized, or heavily redacted samples.

## Local Watch Data Access

Real COROS access should stay local to your machine through your MCP or CLI configuration; Garmin tokens stay local under `~/.garmintokens`. This skill only documents how an agent should use that local toolchain; it does not require credentials to be stored in the repository.

FIT downloads are opt-in for a key activity analysis. Do not download or retain them for ordinary daily checks.

## Local Data Archive

`scripts/archive_snapshot.py` writes slim training snapshots to a local archive outside this repository (default `~/.running-coach/archive/`). The archive never contains FIT binaries, GPS traces, second-by-second series, tokens, or menstrual-cycle data; a redaction scan rejects writes that contain forbidden keys or raw numeric streams. Pointing the archive inside a repository checkout is not supported — do not commit archive files.

## 个人信息保护（中国内地用户）

健康与运动数据在中国内地《个人信息保护法》下属于敏感个人信息。本 skill 对应的做法：

- 真实健康数据仅在本机处理与留存：MCP/CLI 本地缓存、`~/.running-coach/` 下的数据档案与运动员档案；不出境、不上传本仓库。
- 数据档案写入前经脱敏扫描，凭证、坐标、逐秒原始序列与经期数据一律拒绝入档。
- 删除即删除：`~/.running-coach/` 下按月归档，删除对应文件即可，无外部副本。

## Health Disclaimer

The skill provides training guidance, not medical advice. For chest pain, fainting, abnormal heart rhythm, acute injury, persistent pain, or other concerning symptoms, stop training and consult a qualified professional.
