"""Data-source definitions for the BUPT campus crawler."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DataSource:
    """Describes a single BUPT web data source to crawl."""

    name: str
    base_url: str
    category: str
    crawl_interval_minutes: int
    selectors: dict
    requires_auth: bool = False


BUPT_DATA_SOURCES: list[DataSource] = [
    DataSource(
        name="教务通知",
        base_url="https://jwc.bupt.edu.cn",
        category="academic",
        crawl_interval_minutes=10,
        selectors={
            "list": "ul.news-list li a",
            "title": "h1.article-title",
            "content": "div.article-content",
            "date": "span.publish-date",
            "author": "span.article-author",
        },
    ),
    DataSource(
        name="校园新闻",
        base_url="https://news.bupt.edu.cn",
        category="news",
        crawl_interval_minutes=60,
        selectors={
            "list": "div.news-list ul li a",
            "title": "h1.news-title",
            "content": "div.news-content",
            "date": "span.news-date",
            "author": "span.news-author",
        },
    ),
    DataSource(
        name="图书馆",
        base_url="https://lib.bupt.edu.cn",
        category="library",
        crawl_interval_minutes=120,
        selectors={
            "list": "ul.notice-list li a",
            "title": "h2.notice-title",
            "content": "div.notice-body",
            "date": "span.notice-date",
            "author": "span.notice-author",
        },
    ),
    DataSource(
        name="信息门户",
        base_url="https://my.bupt.edu.cn",
        category="portal",
        crawl_interval_minutes=30,
        requires_auth=True,
        selectors={
            "list": "div.portal-list a.item-link",
            "title": "h1.portal-title",
            "content": "div.portal-content",
            "date": "span.portal-date",
            "author": "span.portal-author",
        },
    ),
    DataSource(
        name="学生活动",
        base_url="https://youth.bupt.edu.cn",
        category="activity",
        crawl_interval_minutes=60,
        selectors={
            "list": "ul.activity-list li a",
            "title": "h1.activity-title",
            "content": "div.activity-content",
            "date": "span.activity-date",
            "author": "span.activity-author",
        },
    ),
    DataSource(
        name="研究生院",
        base_url="https://grs.bupt.edu.cn",
        category="academic",
        crawl_interval_minutes=30,
        selectors={
            "list": "ul.post-list li a",
            "title": "h1.post-title",
            "content": "div.post-content",
            "date": "span.post-date",
            "author": "span.post-author",
        },
    ),
    DataSource(
        name="FAQ/办事大厅",
        base_url="https://service.bupt.edu.cn",
        category="service",
        crawl_interval_minutes=1440,
        selectors={
            "list": "div.service-list a.service-item",
            "title": "h1.service-title",
            "content": "div.service-detail",
            "date": "span.service-date",
            "author": "span.service-author",
        },
    ),
]
