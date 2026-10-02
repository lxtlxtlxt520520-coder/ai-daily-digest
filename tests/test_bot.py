import unittest
from datetime import datetime, timezone
from digest.bot import daily_due, process_batch

NOW = datetime(2026, 10, 2, 0, 17, tzinfo=timezone.utc)
OWNER = 12345


def update(number, text="/digest"):
    return {"update_id": number, "message": {"text": text, "date": int(NOW.timestamp()), "chat": {"type": "private", "id": OWNER}, "from": {"id": OWNER, "is_bot": False}}}


class BotTests(unittest.TestCase):
    def test_delayed_schedule_preserves_commands_within_one_day(self):
        generated = []
        delayed = update(10)
        delayed["message"]["date"] -= 7200
        process_batch([delayed], {"offset": 0}, lambda s: None, lambda o: None, OWNER, lambda t: None,
                      lambda: generated.append(True), NOW)
        self.assertEqual(generated, [True])
        delayed = update(11)
        delayed["message"]["date"] -= 90000
        process_batch([delayed], {"offset": 0}, lambda s: None, lambda o: None, OWNER, lambda t: self.fail("old command"),
                      lambda: self.fail("old command"), NOW)

    def test_ack_before_generation_and_batch_coalesced(self):
        calls = []
        state = {"offset": 0}
        process_batch([update(11), update(10)], state, lambda s: calls.append("persist"), lambda o: calls.append("ack"),
                      OWNER, lambda t: calls.append("reply"), lambda: calls.append("generate"), NOW)
        self.assertEqual(calls, ["persist", "ack", "reply", "generate"])
        self.assertEqual(state["offset"], 12)

    def test_cache_and_telegram_cursor_deduplicate(self):
        calls = []
        process_batch([update(10)], {"offset": 11}, lambda s: None, lambda o: None, OWNER, calls.append, lambda: self.fail("must not generate"), NOW)
        self.assertEqual(calls, [])

    def test_morning_daily_only_once_and_same_pass_command_not_extra_call(self):
        state, generated = {"offset": 0}, []
        process_batch([update(10)], state, lambda s: None, lambda o: None, OWNER, lambda t: None, lambda: generated.append(True), NOW, daily=True)
        self.assertEqual(generated, [True])
        self.assertFalse(daily_due(state, NOW))

    def test_no_message_and_not_morning_does_not_call_model(self):
        earlier = datetime(2026, 10, 1, 23, 0, tzinfo=timezone.utc)
        process_batch([], {"offset": 0}, lambda s: None, lambda o: None, OWNER, lambda t: self.fail("must not reply"),
                      lambda: self.fail("must not generate"), earlier, daily=True)

    def test_ack_failure_prevents_paid_side_effect(self):
        def fail(offset):
            raise TimeoutError()
        with self.assertRaises(TimeoutError):
            process_batch([update(10)], {"offset": 0}, lambda s: None, fail, OWNER, lambda t: self.fail("must not reply"),
                          lambda: self.fail("must not generate"), NOW)
