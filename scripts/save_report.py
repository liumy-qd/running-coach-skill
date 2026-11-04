#!/usr/bin/env python3
"""保存带时间戳文件名的 running-coach Markdown 报告。"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import sys


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "running-report"


def main() -> int:
    parser = argparse.ArgumentParser(description="保存 running-coach Markdown 报告。")
    parser.add_argument("--title", default="running-report", help="用于文件名的报告标题。")
    parser.add_argument("--output-dir", default=".", help="报告保存目录。")
    parser.add_argument("--stdin", action="store_true", help="从 stdin 读取 Markdown 内容。")
    args = parser.parse_args()

    content = sys.stdin.read() if args.stdin else ""
    if not content.strip():
        parser.error("使用 --stdin 时必须从 stdin 提供报告内容")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = output_dir / f"{timestamp}-{slugify(args.title)}.md"
    output_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
