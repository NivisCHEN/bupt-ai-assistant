#!/usr/bin/env python3
"""手动触发北邮门户爬虫（需要浏览器，基于 DrissionPage）。

使用方法：
    python scripts/run_portal_crawler.py --username 2021XXXXX --password yourpwd
    python scripts/run_portal_crawler.py --username 2021XXXXX --password yourpwd --type news
    python scripts/run_portal_crawler.py --username 2021XXXXX --password yourpwd --pages 3
    python scripts/run_portal_crawler.py --force-login   # 忽略已保存 Cookie，强制重新登录

爬完后需要重建索引：
    python scripts/build_knowledge_base.py --source file

环境变量：
    BUPT_BROWSER_PATH   指定浏览器可执行文件路径（不填则自动探测）
    BUPT_PORTAL_USER    门户账号（可代替 --username）
    BUPT_PORTAL_PASS    门户密码（可代替 --password）

依赖安装：
    pip install DrissionPage trafilatura
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DrissionPage 北邮门户爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--username", "-u",
        default=os.environ.get("BUPT_PORTAL_USER", ""),
        help="北邮学号（也可用环境变量 BUPT_PORTAL_USER）",
    )
    parser.add_argument(
        "--password", "-p",
        default=os.environ.get("BUPT_PORTAL_PASS", ""),
        help="统一认证密码（也可用环境变量 BUPT_PORTAL_PASS）",
    )
    parser.add_argument(
        "--type", "-t",
        dest="portal_type",
        choices=["notice", "news", "both"],
        default="notice",
        help="抓取类型：notice=校内通知  news=校内新闻  both=两者都抓（默认 notice）",
    )
    parser.add_argument(
        "--pages", "-n",
        type=int,
        default=1,
        metavar="N",
        help="每个类型抓取列表页数（默认 1）",
    )
    parser.add_argument(
        "--force-login",
        action="store_true",
        help="忽略已保存的 Cookie，强制重新登录",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式（不显示浏览器窗口）；手动登录时勿用",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=str(PROJECT_ROOT / "data" / "config.json"),
        help="从 JSON 配置文件读取账号密码（优先级低于命令行参数）",
    )
    args = parser.parse_args()

    # Try reading credentials from config file if not supplied on CLI
    username = args.username
    password = args.password
    if (not username or not password) and Path(args.config).exists():
        try:
            cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
            username = username or cfg.get("portal_username", "")
            password = password or cfg.get("portal_password", "")
        except Exception:
            pass

    if not username or not password:
        logger.error(
            "请提供账号和密码：--username / --password 或环境变量 "
            "BUPT_PORTAL_USER / BUPT_PORTAL_PASS，或 data/config.json"
        )
        sys.exit(1)

    try:
        from src.crawler.drission_spider import DrissionPortalSpider
    except ImportError as exc:
        logger.error("导入失败：{}。请执行 pip install DrissionPage trafilatura", exc)
        sys.exit(1)

    spider = DrissionPortalSpider(
        username=username,
        password=password,
        force_login=args.force_login,
        headless=args.headless,
    )

    types_to_run = ["notice", "news"] if args.portal_type == "both" else [args.portal_type]
    total_new = 0

    for ptype in types_to_run:
        logger.info("开始爬取：{}", ptype)
        docs = spider.crawl(portal_type=ptype, max_pages=args.pages)
        logger.info("本类型新增：{} 条", len(docs))
        total_new += len(docs)

    logger.info("全部完成，共新增 {} 条数据", total_new)

    if total_new > 0:
        print()
        print("=" * 55)
        print("下一步：重建知识库索引")
        print("  python scripts/build_knowledge_base.py --source file")
        print("=" * 55)


if __name__ == "__main__":
    main()
