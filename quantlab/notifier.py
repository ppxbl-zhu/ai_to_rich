"""Notification boundary. Credentials are accepted only through environment variables."""

import json
import os
from urllib.request import Request, urlopen


def publish_local(message: str) -> str:
    return message


def publish_pushplus(title: str, message: str, timeout: float = 20) -> bool:
    """Send through PushPlus when PUSHPLUS_TOKEN is configured; otherwise skip safely."""
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        return False
    body = json.dumps({"token": token, "title": title, "content": message, "template": "markdown"}).encode("utf-8")
    request = Request("https://www.pushplus.plus/send", data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    if result.get("code") != 200:
        raise RuntimeError(f"PushPlus 推送失败：{result.get('msg', '未知错误')}")
    return True
