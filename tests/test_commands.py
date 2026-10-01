import unittest
from datetime import datetime, timezone
from digest.commands import handle

NOW = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
OWNER = 12345


def update(text, chat_id=OWNER, sender_id=OWNER, kind="private", age=0):
    return {"message": {"text": text, "date": int(NOW.timestamp()) - age,
                        "chat": {"id": chat_id, "type": kind}, "from": {"id": sender_id, "is_bot": False}}}


class CommandTests(unittest.TestCase):
    def test_start_and_ordinary_messages_reply_without_model(self):
        for text in ["/start", "/help", "你好", "帮助"]:
            sent = []
            self.assertTrue(handle(update(text), OWNER, sent.append, lambda: self.fail("must not generate"), NOW))
            self.assertEqual(len(sent), 1)

    def test_chinese_and_slash_commands_generate(self):
        for text in ["/digest", "/digest@lxt_ai_daily_digest_bot", "生成日报", "立即生成日报"]:
            generated = []
            self.assertTrue(handle(update(text), OWNER, lambda text: self.fail("must not chat"), lambda: generated.append(True), NOW))
            self.assertEqual(generated, [True])

    def test_other_chats_and_groups_and_senders_cannot_trigger(self):
        for message in [update("/digest", chat_id=999), update("/digest", sender_id=999), update("/digest", kind="group")]:
            self.assertFalse(handle(message, OWNER, lambda text: self.fail("must not reply"), lambda: self.fail("must not generate"), NOW))

    def test_old_commands_and_future_commands_not_replayed(self):
        for age in [601, -61]:
            self.assertFalse(handle(update("/digest", age=age), OWNER, lambda text: self.fail("must not reply"), lambda: self.fail("must not generate"), NOW))
