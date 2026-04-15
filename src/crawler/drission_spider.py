"""DrissionPage-based portal spider for BUPT internal pages.

Used for sources that require browser-based authentication (my.bupt.edu.cn).
Handles the JS-heavy unified-auth login page with its nested iframe,
cookie reuse across runs, and auto-detection of campus vs. off-campus
network.

Requires optional dependencies:
    pip install DrissionPage trafilatura
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

# ──────────────────────────────────────────────────────────────────────
# File paths (relative to project root)
# ──────────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COOKIE_FILE = _PROJECT_ROOT / "data" / "bupt_cookie.json"
PORTAL_DATA_FILE = _PROJECT_ROOT / "data" / "portal_data.json"

LOGIN_URL = (
    "https://auth.bupt.edu.cn/authserver/login"
    "?service=http%3A%2F%2Fmy.bupt.edu.cn%2F"
)
VPN_URL = "https://webvpn.bupt.edu.cn/login"

# Public portal list pages (no auth needed just to read, but login required
# to actually see the content).
PORTAL_URLS: dict[str, str] = {
    "notice": "http://my.bupt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154",
    "news":   "http://my.bupt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1221",
}

# How many characters of body text to keep per article.  500 is too short
# for RAG; 2 000 gives the model enough context without ballooning the index.
CONTENT_MAX_CHARS = 2000


# ──────────────────────────────────────────────────────────────────────
# Browser path helpers
# ──────────────────────────────────────────────────────────────────────

def _find_browser_path() -> Optional[str]:
    """Return a usable browser executable path or None to let DrissionPage
    auto-detect.  Reads BUPT_BROWSER_PATH env var first (highest priority)."""
    env_path = os.environ.get("BUPT_BROWSER_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    candidates: list[str] = []
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
        ]

    for p in candidates:
        if Path(p).exists():
            return p
    return None  # let DrissionPage try its own detection


# ──────────────────────────────────────────────────────────────────────
# Utility helpers (module-level so they can be used independently)
# ──────────────────────────────────────────────────────────────────────

def check_is_campus_network() -> bool:
    """Return True if the machine can reach my.bupt.edu.cn directly."""
    logger.info("检测网络环境…")
    try:
        urllib.request.urlopen("http://my.bupt.edu.cn/", timeout=3)
        logger.info("当前为校内网环境")
        return True
    except Exception:
        logger.info("当前为校外环境")
        return False


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _normalize_url(href: str) -> str:
    if href.startswith("/"):
        return "http://my.bupt.edu.cn" + href
    if href.startswith("./"):
        return "http://my.bupt.edu.cn" + href[1:]
    return href


# ──────────────────────────────────────────────────────────────────────
# Main class
# ──────────────────────────────────────────────────────────────────────

class DrissionPortalSpider:
    """Browser-based spider for BUPT portal pages that require login.

    Example::

        spider = DrissionPortalSpider(username="2021XXXXX", password="***")
        docs = spider.crawl(portal_type="notice", max_pages=2)
        # docs is a list of dicts compatible with build_knowledge_base.py

    Env-vars:
        BUPT_BROWSER_PATH   Override browser executable (default: auto-detect)
    """

    def __init__(
        self,
        username: str,
        password: str,
        *,
        force_login: bool = False,
        headless: bool = False,
    ) -> None:
        self.username = username
        self.password = password
        self.force_login = force_login
        self.headless = headless
        self._page = None  # ChromiumPage, created lazily

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crawl(
        self,
        portal_type: str = "notice",
        max_pages: int = 1,
    ) -> list[dict]:
        """Crawl the BUPT portal and return documents in the standard format.

        Args:
            portal_type: ``"notice"`` (校内通知) or ``"news"`` (校内新闻).
            max_pages:   Number of list pages to paginate through.

        Returns:
            List of dicts with keys: id, title, content, source_url,
            category, published_at, attachments.
        """
        try:
            from DrissionPage import ChromiumOptions, ChromiumPage
        except ImportError:
            logger.error(
                "DrissionPage 未安装。请执行: pip install DrissionPage trafilatura"
            )
            return []

        # Check trafilatura availability
        try:
            import trafilatura
            _use_trafilatura = True
        except ImportError:
            _use_trafilatura = False
            logger.debug("trafilatura 未安装，降级使用 BeautifulSoup 提取正文")

        # Build browser options
        co = ChromiumOptions()
        browser_path = _find_browser_path()
        if browser_path:
            co.set_browser_path(browser_path)
            logger.debug("使用浏览器：{}", browser_path)
        else:
            logger.debug("未指定浏览器路径，由 DrissionPage 自动探测")

        co.set_argument("--disable-blink-features=AutomationControlled")
        co.set_user_agent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        if self.headless:
            co.headless(True)

        page = ChromiumPage(co)
        self._page = page

        try:
            if not self._login(page):
                logger.error("登录失败，停止爬取")
                return []

            return self._crawl_pages(
                page, portal_type, max_pages, _use_trafilatura
            )
        finally:
            page.quit()
            self._page = None

    # ------------------------------------------------------------------
    # Login flow
    # ------------------------------------------------------------------

    def _login(self, page) -> bool:
        """Try cookie reuse → auto password → manual, in that order."""
        is_campus = check_is_campus_network()

        # 1. Cookie reuse
        if not self.force_login:
            cookies = self._load_cookies()
            if cookies:
                logger.info("发现已保存 Cookie（{}个），尝试复用…", len(cookies))
                page.set.cookies(cookies)
                page.get("http://my.bupt.edu.cn/")
                time.sleep(3)
                if self._is_logged_in(page):
                    logger.info("Cookie 有效，免登录成功")
                    return True
                logger.warning("Cookie 已失效，清除并重新登录")
                self._delete_cookies()

        # 2. Auto password (campus network only)
        if is_campus and not self.force_login:
            if self._auto_login(page):
                self._save_cookies(page)
                return True
            logger.warning("自动密码登录失败，切换手动登录")

        # 3. Manual fallback
        return self._manual_login(page, is_campus)

    def _auto_login(self, page) -> bool:
        logger.info("尝试自动密码登录…")
        try:
            page.get(LOGIN_URL)
            time.sleep(5)

            iframe = page.get_frame("loginIframe")
            if not iframe:
                logger.warning("未找到 loginIframe")
                return False

            # Switch to password tab
            switch_btn = iframe.ele("@i18n=login.type.password")
            if switch_btn:
                switch_btn.click(by_js=True)
                time.sleep(2)

            username_input = iframe.ele("@id=username") or iframe.ele("@name=username")
            password_input = iframe.ele("@id=password") or iframe.ele("@name=password")
            if not username_input or not password_input:
                logger.warning("未找到账号/密码输入框")
                return False

            username_input.clear()
            username_input.input(self.username)
            time.sleep(0.5)
            password_input.clear()
            password_input.input(self.password)
            time.sleep(1)

            submit_btn = iframe.ele("@i18n=login.form.btn.login")
            if submit_btn:
                submit_btn.click(by_js=True)
            else:
                password_input.input("\n")
            time.sleep(5)

            if self._is_logged_in(page):
                logger.info("自动密码登录成功")
                return True
            logger.warning("登录后 URL 仍在认证页：{}", page.url)
            return False

        except Exception as exc:
            logger.exception("自动登录异常：{}", exc)
            return False

    def _manual_login(self, page, is_campus: bool) -> bool:
        target = LOGIN_URL if is_campus else VPN_URL
        page.get(target)
        logger.info(
            "请在弹出的浏览器窗口中手动完成登录（扫码或输密码均可），等待 120 秒…"
        )
        start = time.time()
        while time.time() - start < 120:
            if self._is_logged_in(page):
                logger.info("手动登录成功")
                self._save_cookies(page)
                return True
            time.sleep(2)
        logger.error("等待手动登录超时（120s）")
        return False

    @staticmethod
    def _is_logged_in(page) -> bool:
        url = page.url
        if "authserver" in url or "login" in url.lower():
            return False
        if "my.bupt.edu.cn" in url:
            try:
                return bool(page.ele("text:退出") or page.ele("text:注销"))
            except Exception:
                return False
        return False

    # ------------------------------------------------------------------
    # Cookie persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _save_cookies(page) -> None:
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cookies = page.cookies(all_domains=True, all_info=True)
        clean = [
            {
                "name": c.get("name"),
                "value": c.get("value"),
                "domain": c.get("domain"),
                "path": c.get("path", "/"),
                "secure": c.get("secure", False),
                "httpOnly": c.get("httpOnly", False),
            }
            for c in cookies
        ]
        COOKIE_FILE.write_text(
            json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Cookie 已保存（{}个）→ {}", len(clean), COOKIE_FILE)

    @staticmethod
    def _load_cookies() -> list[dict] | None:
        if COOKIE_FILE.exists():
            try:
                return json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    @staticmethod
    def _delete_cookies() -> None:
        if COOKIE_FILE.exists():
            COOKIE_FILE.unlink()
            logger.info("已删除失效 Cookie 文件：{}", COOKIE_FILE)

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------

    def _crawl_pages(
        self,
        page,
        portal_type: str,
        max_pages: int,
        use_trafilatura: bool,
    ) -> list[dict]:
        target_url = PORTAL_URLS.get(portal_type, PORTAL_URLS["notice"])
        label = "校内通知" if portal_type == "notice" else "校内新闻"
        logger.info("目标：【{}】 {}", label, target_url)

        page.get(target_url)
        time.sleep(3)

        if "authserver" in page.url:
            logger.error("被重定向回登录页，会话已失效；请删除 Cookie 后重新运行")
            return []

        # Load existing data to enable deduplication
        existing = self._load_existing_data()
        seen_hashes = {item.get("id") for item in existing}

        all_new: list[dict] = []

        for current_page in range(1, max_pages + 1):
            logger.info("第 {}/{} 页", current_page, max_pages)

            # Locate article links
            items = page.eles('xpath://a[contains(@href, "content.jsp")]')
            if not items:
                container = page.ele(".news_list") or page.ele(".list")
                if container:
                    items = container.eles("tag:a")
            logger.debug("找到 {} 个候选链接", len(items))

            for a_tag in items:
                href = a_tag.attr("href") or ""
                title = a_tag.text.strip()
                if not (title and len(title) > 5 and "content.jsp" in href):
                    continue

                url = _normalize_url(href)
                doc_id = _url_hash(url)
                if doc_id in seen_hashes:
                    logger.debug("跳过重复：{}", title[:30])
                    continue

                doc = self._fetch_article(page, url, title, portal_type, use_trafilatura)
                if doc:
                    all_new.append(doc)
                    seen_hashes.add(doc_id)
                    logger.info("✓ {}", title[:40])

            # Pagination
            if current_page < max_pages:
                next_btn = page.ele("text:下页") or page.ele("text:下一页")
                if next_btn:
                    next_btn.click()
                    time.sleep(3)
                else:
                    logger.info("无下一页，提前结束分页")
                    break

        # Append and persist
        all_data = existing + all_new
        self._save_all_data(all_data)
        logger.info(
            "爬取完成：本次新增 {} 条，累计 {} 条 → {}",
            len(all_new), len(all_data), PORTAL_DATA_FILE,
        )
        return all_new

    @staticmethod
    def _fetch_article(
        page, url: str, title: str, portal_type: str, use_trafilatura: bool
    ) -> dict | None:
        """Open article in a new tab, extract content, return a doc dict."""
        try:
            page.new_tab(url)
            tab = page.get_tab(page.latest_tab)
            time.sleep(1.5)

            content = ""
            if use_trafilatura:
                try:
                    import trafilatura
                    content = trafilatura.extract(tab.html, output_format="text") or ""
                except Exception:
                    pass
            if not content:
                el = tab.ele(".v_news_content") or tab.ele(".content")
                content = el.text if el else ""

            # Attachments
            attachments = [
                a.attr("href")
                for a in tab.eles("tag:a")
                if a.attr("href") and (
                    "download.jsp" in (a.attr("href") or "")
                    or (a.attr("href") or "").endswith((".pdf", ".doc", ".docx"))
                )
            ]

            doc = {
                "id": _url_hash(url),
                "title": title,
                "content": content[:CONTENT_MAX_CHARS],
                "source_url": tab.url,
                "category": portal_type,
                "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "attachments": attachments,
            }
            tab.close()
            time.sleep(0.5)
            return doc

        except Exception as exc:
            logger.error("抓取失败 {}：{}", url, exc)
            return None

    # ------------------------------------------------------------------
    # Data persistence helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_existing_data() -> list[dict]:
        if PORTAL_DATA_FILE.exists():
            try:
                return json.loads(PORTAL_DATA_FILE.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    @staticmethod
    def _save_all_data(data: list[dict]) -> None:
        PORTAL_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        PORTAL_DATA_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
