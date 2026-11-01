"""Tests for spike.py's page classification. Run with:  .venv/Scripts/python -m unittest"""

import unittest

from spike import classify


class ClassifyTests(unittest.TestCase):
    def test_big_page_mentioning_captcha_is_ok(self):
        # Regression: eMAG and Storia product pages load reCAPTCHA scripts.
        html = "<html>" + "x" * 300_000 + "<script src='recaptcha.js'></script></html>"
        self.assertEqual(classify(200, html), "ok")

    def test_small_captcha_page_is_blocked(self):
        html = "<html><title>Attention Required!</title>Please complete the captcha" + " " * 600
        self.assertEqual(classify(200, html), "blocked")

    def test_forbidden_status_is_blocked(self):
        self.assertEqual(classify(403, "<html>" + " " * 600 + "</html>"), "blocked")

    def test_not_found_is_removed(self):
        self.assertEqual(classify(404, "not found"), "removed")

    def test_tiny_page_is_empty(self):
        self.assertEqual(classify(200, "<html></html>"), "empty")


if __name__ == "__main__":
    unittest.main()
