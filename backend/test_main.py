
import unittest
from main import select_today_nikki_from_template


class TestMain(unittest.TestCase):

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
