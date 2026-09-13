
import unittest
import datetime
from main import create_template_batch_trigger, jst, select_today_nikki_from_template


class TestMain(unittest.TestCase):

    def test_template_batch_runs_at_midnight_jst(self):
        trigger = create_template_batch_trigger()
        now = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)

        next_run = trigger.get_next_fire_time(None, now)

        self.assertEqual(datetime.datetime(2026, 1, 2, 0, 0, tzinfo=jst), next_run)
        self.assertEqual(
            datetime.datetime(2026, 1, 1, 15, 0, tzinfo=datetime.timezone.utc),
            next_run.astimezone(datetime.timezone.utc),
        )

    def test_select_today_nikki_from_template(self):
        testcases=[
            """
・AAAA
　▶️BBBB
✅CCCC
　▶️DDDD
　　▶️EEEE
            """
        ]
        expected_results=[
            """▶️BBBB
▶️DDDD
▶️EEEE"""
        ]
        for testcase,expected in zip(testcases,expected_results):
            actual = select_today_nikki_from_template(testcase)
            self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
