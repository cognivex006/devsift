import json
import unittest

from devsift.redaction import RedactionError, Redactor


class RedactionTests(unittest.TestCase):
    def test_explicit_values_are_masked_across_nested_values_and_keys(self):
        secret = "fixture" + "PrivateValue"
        original = {"before": [secret, {secret: "proposal " + secret}], "password": "unknown-value"}
        result = Redactor((secret,)).redact(original)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn("unknown-value", json.dumps(result))
        self.assertEqual(original["before"][0], secret)

    def test_bounded_common_patterns_and_idempotence(self):
        samples = ["password='dummy-value'", "Authorization: Bearer " + "z" * 30,
                   "gh" + "p_" + "a" * 36, "AK" + "IA" + "A" * 16,
                   "https://user:dummy-value@example.invalid/path",
                   "-----BEGIN PRIVATE KEY-----\nfixture-only\n-----END PRIVATE KEY-----"]
        redactor = Redactor()
        for sample in samples:
            with self.subTest(sample=sample):
                result = redactor.text(sample)
                self.assertNotEqual(result, sample)
                self.assertIn("[REDACTED]", result)
                self.assertEqual(redactor.text(result), result)

    def test_failures_do_not_echo_secret_or_object_repr(self):
        class Unsafe:
            def __repr__(self):
                raise AssertionError("must not invoke untrusted repr")
        cyclic = []
        cyclic.append(cyclic)
        for value in (Unsafe(), cyclic, float("nan")):
            with self.assertRaises(RedactionError) as error:
                Redactor().redact(value)
            self.assertEqual(str(error.exception), "unsupported or excessive redaction input")
        self.assertNotIn("PrivateValue", repr(Redactor(("PrivateValue",))))

    def test_marker_substrings_and_overlapping_explicit_values_are_idempotent(self):
        redactor = Redactor(("REDACTED", "abcdef", "abc"))
        once = redactor.text("abcdef abc [REDACTED]")
        self.assertEqual(once, "[REDACTED] [REDACTED] [REDACTED]")
        self.assertEqual(redactor.text(once), once)
        self.assertEqual(Redactor(("SensitiveValue", "RED")).text("SensitiveValue"), "[REDACTED]")

    def test_colliding_redacted_keys_and_excessive_depth_fail_closed(self):
        with self.assertRaises(RedactionError):
            Redactor(("one", "two")).redact({"one": 1, "two": 2})
        value = "leaf"
        for _ in range(34):
            value = [value]
        with self.assertRaises(RedactionError):
            Redactor().redact(value)

    def test_explicit_secret_containing_marker_is_masked_before_marker_preservation(self):
        secret = "abc[REDACTED]xyz"
        redactor = Redactor((secret, "RED"))
        self.assertEqual(redactor.text(secret), "[REDACTED]")
        self.assertEqual(redactor.text(redactor.text(secret)), "[REDACTED]")

    def test_context_slice_masks_overlapping_sensitive_spans_using_original_offsets(self):
        secret = "fixture" + "SensitiveValue"
        value = "password='" + secret + "' visible"
        self.assertEqual(Redactor().slice(value, 10, 31), "[REDACTED]")
        self.assertEqual(Redactor().slice(value, 15, 20), "[REDACTED]")
        self.assertEqual(Redactor().slice(value, 10, len(value)), "[REDACTED] visible")
        self.assertEqual(Redactor().slice(value, 15, 15), "")
        self.assertEqual(Redactor().slice(value, 33, len(value)), "visible")


if __name__ == "__main__":
    unittest.main()
