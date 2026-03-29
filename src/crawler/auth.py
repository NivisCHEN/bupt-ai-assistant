"""北邮统一认证登录模块"""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup
from loguru import logger

LOGIN_URL = "https://auth.bupt.edu.cn/authserver/login"


async def login_bupt_portal(username: str, password: str) -> dict:
    """登录北邮统一认证，返回 cookies。

    Args:
        username: 学号
        password: 密码

    Returns:
        认证成功后的 cookies 字典。

    Raises:
        ValueError: 用户名或密码错误。
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # 1. GET 登录页，解析隐藏表单字段（lt, execution 等）
        resp = await client.get(LOGIN_URL)
        soup = BeautifulSoup(resp.text, "html.parser")

        lt = soup.find("input", {"name": "lt"})
        execution = soup.find("input", {"name": "execution"})

        # 2. POST 提交账号密码
        payload = {
            "username": username,
            "password": password,
            "lt": lt["value"] if lt else "",
            "execution": execution["value"] if execution else "",
            "_eventId": "submit",
        }
        login_resp = await client.post(LOGIN_URL, data=payload)

        if "统一身份认证" in login_resp.text:
            raise ValueError("用户名或密码错误")

        logger.info("北邮统一认证登录成功: {}", username)
        return dict(client.cookies)
