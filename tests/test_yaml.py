
import unittest

def line_col(item):
    return item.line, item.column

class TestFromYaml(unittest.TestCase):
    def setUp(self):
        from bert.yaml import from_yaml
        self.from_yaml = from_yaml

    def test_null(self):
        self.assertEqual(self.from_yaml("test: "), {"test": None})

    def test_str(self):
        result = self.from_yaml("\ntest: 'abc'")
        self.assertEqual(result, {"test": "abc"})
        self.assertEqual(line_col(result["test"]), (2, 6))

    def test_int(self):
        result = self.from_yaml("\ntest: 77")
        self.assertEqual(result, {"test": 77})
        self.assertEqual(line_col(result["test"]), (2, 6))

    def test_float(self):
        result = self.from_yaml("\ntest: 1.e+7")
        self.assertEqual(result, {"test": 1e7})
        self.assertEqual(line_col(result["test"]), (2, 6))

    def test_dict(self):
        result = self.from_yaml("""
        test:
            a: b
            c: f
        """)
        self.assertEqual(result, {"test" : {"a" : "b", "c" : "f"}})
        self.assertEqual(line_col(result["test"]), (3, 12))
        self.assertEqual(line_col(result["test"]["c"]), (4, 15))
