
import unittest

class TestExpectFileMode(unittest.TestCase):
    def setUp(self):
        from bert.utils import expect_file_mode
        self.expect_file_mode = expect_file_mode

    def test_nil(self):
        self.assertEqual(self.expect_file_mode(None), None)
        self.assertEqual(self.expect_file_mode(""), None)

    def test_int(self):
        self.assertEqual(self.expect_file_mode(0o422), 0o422)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            self.expect_file_mode("o=u")

        with self.assertRaises(ValueError):
            self.expect_file_mode("x=g")

        with self.assertRaises(ValueError):
            self.expect_file_mode("abc")

    def test_str(self):
        self.assertEqual(self.expect_file_mode("o=x"), 0o001)
        self.assertEqual(self.expect_file_mode("o=rwx"), 0o007)
        self.assertEqual(self.expect_file_mode("o=rw"), 0o006)
        self.assertEqual(self.expect_file_mode("u=rwx,g=rx,o=rx"), 0o755)
        self.assertEqual(self.expect_file_mode("g=rx,u=rwx,o=rx"), 0o755)
        self.assertEqual(self.expect_file_mode("u=r,g=r,o=r"), 0o444)
