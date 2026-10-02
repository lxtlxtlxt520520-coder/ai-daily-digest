"""Only the configured owner's private chat can request a paid digest."""
from datetime import datetime, timezone

HELP = "你好，我是 AI 与成长日报机器人。\n\n/digest 或发送「生成日报」：生成个人精选日报\n/help：查看使用方式\n\n目标：GitHub项目3条、AI技巧2条、个人成长2条，健康、科研、心理学各1条；重大AI事件有才报，不足时少报。AI技巧采用免费作者精选，不代表X高赞榜。\n\n每天北京时间早上7点触发自动日报；GitHub调度与生成可能延迟。约每5分钟检查消息，可能因调度延迟更久。"


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
