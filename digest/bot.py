"""One polling pass for GitHub Actions. No persistent Mac service or chat transcript."""
import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .commands import handle
from .run import SHANGHAI, StopRun, post


def load_cursor(path):
    if not path.exists():
        return {"offset": 0, "daily_attempt_date": None}
    state = json.loads(path.read_text())
    if not isinstance(state, dict) or not isinstance(state.get("offset"), int) or state["offset"] < 0:
        raise StopRun("Invalid command cursor")
    return state


def save_cursor(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state) + "\n")
    temporary.replace(path)


def daily_due(state, now):
    local = now.astimezone(SHANGHAI)
    return (local.hour, local.minute) >= (8, 17) and state.get("daily_attempt_date") != local.date().isoformat()


def process_batch(updates, state, persist, acknowledge, owner_id, send, generate, now, daily=False):
    pending = sorted([u for u in updates if isinstance(u.get("update_id"), int) and u["update_id"] >= state["offset"]], key=lambda u: u["update_id"])
    if pending:
        state["offset"] = pending[-1]["update_id"] + 1
        persist(state)
        # Acknowledge at Telegram before side effects. Lost caches cannot replay these commands.
        acknowledge(state["offset"])
    requested = False
    def request_digest():
        nonlocal requested
        if not requested:
            send("已收到，正在采集最新资讯并生成中文日报，请稍等。")
            requested = True
    handled = sum(handle(update, owner_id, send, request_digest, now, max_age=3600) for update in pending)
    automatic = daily and daily_due(state, now)
    if automatic:
        state["daily_attempt_date"] = now.astimezone(SHANGHAI).date().isoformat()
        persist(state)  # Do not automatically retry the daily model call after an uncertain failure.
    if requested or automatic:
        generate()
    return {"messages_handled": handled, "digest_requested": requested, "daily_attempt": automatic}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily", action="store_true", help="Also send the once-daily morning digest")
    args = parser.parse_args()
    for name in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DEEPSEEK_API_KEY"]:
        if not os.environ.get(name):
            raise StopRun("Missing required Secret: " + name)
    owner_id = int(os.environ["TELEGRAM_CHAT_ID"])
    endpoint = "https://api.telegram.org/bot" + os.environ["TELEGRAM_BOT_TOKEN"] + "/"
    path = Path("state/bot-cursor.json")
    output = Path("output")
    output.mkdir(exist_ok=True)
    with (output / ".bot.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def api(method, payload):
            result = post(endpoint + method, payload)
            if not result.get("ok"):
                raise StopRun("Telegram did not confirm " + method)
            return result["result"]
        def send(text):
            api("sendMessage", {"chat_id": owner_id, "text": text, "link_preview_options": {"is_disabled": True}})
        def generate():
            result = subprocess.run([sys.executable, "-m", "digest.run", "--live"], capture_output=True, text=True)
            if result.returncode:
                if "No fresh candidates" in result.stderr or "No eligible candidates" in result.stderr or "No important items" in result.stderr:
                    send("暂时没有适合生成日报的新资讯，未补入旧闻。稍后可以再发送 /digest。")
                    return
                # digest.run emits only controlled error text, never tokens or response bodies.
                reason = result.stderr.strip()[:300]
                if "HTTP 401" in reason:
                    send("日报暂时无法生成：API 密钥认证失败（401）。请检查 GitHub 中的 DEEPSEEK_API_KEY 和密钥所属平台，修正后再发送 /digest。")
                else:
                    send("日报生成或发送未完成，请稍后发送 /digest 重试。没有自动重试。")
                raise StopRun("Digest subprocess failed with exit code " + str(result.returncode) + ": " + reason)
        state = load_cursor(path)
        updates = api("getUpdates", {"offset": state["offset"], "limit": 100, "timeout": 0, "allowed_updates": ["message"]})
        stats = process_batch(updates, state, lambda state: save_cursor(path, state),
                              lambda offset: api("getUpdates", {"offset": offset, "limit": 1, "timeout": 0}),
                              owner_id, send, generate, datetime.now(timezone.utc), args.daily)
        (output / "commands.json").write_text(json.dumps(stats, indent=2))
        print(json.dumps(stats))


if __name__ == "__main__":
    try:
        main()
    except StopRun as error:
        print("Failed: " + str(error), file=sys.stderr)
        sys.exit(2)
    except Exception as error:
        print("Failed: " + type(error).__name__, file=sys.stderr)
        sys.exit(1)
