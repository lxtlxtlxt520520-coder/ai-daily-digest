"""Only the configured owner's private chat can request a paid digest."""
from datetime import datetime, timezone

HELP = "你好，我是 AI 中文日报机器人。\n\n/digest 或发送「生成日报」：采集最新资讯并生成中文日报\n/help：查看使用方式\n\n约每5分钟检查消息，可能因调度延迟更久；每天早上自动推送日报。"


def handle(update, owner_id, send, generate, now=None, max_age=600):
    message = update.get("message", {})
    chat = message.get("chat", {})
    sender = message.get("from", {})
    if chat.get("type") != "private" or chat.get("id") != owner_id or sender.get("id") != owner_id or sender.get("is_bot"):
        return False
    text = message.get("text", "")
    if not isinstance(text, str):
        return False
    # Reconnecting must not execute a backlog of old paid commands.
    now = now or datetime.now(timezone.utc)
    date = message.get("date")
    if not isinstance(date, int) or not -60 <= now.timestamp() - date <= max_age:
        return False
    command = text.strip().split(maxsplit=1)[0].split("@")[0].lower() if text.strip() else ""
    if command in {"/start", "/help", "帮助", "菜单"}:
        send(HELP)
    elif command in {"/digest", "生成日报", "立即生成日报", "立即生成", "日报", "今日资讯"}:
        generate()
    else:
        send("我已收到消息。发送 /digest 或「生成日报」可以生成最新日报，发送 /help 查看说明。")
    return True
