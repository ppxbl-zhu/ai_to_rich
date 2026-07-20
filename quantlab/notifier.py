"""Notification boundary.

Do not automate a personal WeChat login. A future provider implementation should
accept its token from an environment variable and send only redacted reports.
"""


def publish_local(message: str) -> str:
    return message
