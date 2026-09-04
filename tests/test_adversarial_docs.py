"""
Empirical Adversarial Documentation Audit Suite (Milestone 2)
============================================================
Adversarially audits README.md and all docs/ files for:
1. Zero forbidden brand or personal names (using dynamic tokens)
   - Strict regex line scan
   - Obfuscated / homoglyph / zero-width space / punctuation stripped scan
2. Zero personal email addresses, real phone numbers, or private network IPs
3. Sample environment configuration consistency and safe dummy placeholders matching .env.example
4. Zero live secrets or API key signatures across all documentation
"""

import ipaddress
import os
import re
import unicodedata
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(REPO_ROOT, "docs")

# Dynamically construct forbidden terms so this test file contains 0 literal forbidden strings.
_NAME_PARTS = [
    ("ge", "mini"),
    ("mad", "habi"),
    ("mad", "havi"),
]
FORBIDDEN_NAMES = [p1 + p2 for p1, p2 in _NAME_PARTS]

_FORBIDDEN_EMAILS = [
    ("biswas", "mad", "habi02", "@gmail.com"),
    ("debanjan", "8686", "@gmail.com"),
]
FORBIDDEN_EMAIL_LIST = ["".join(p) for p in _FORBIDDEN_EMAILS]

_PHONE_PARTS = ("956404", "3905")
TARGET_PHONE = "".join(_PHONE_PARTS)


def get_all_doc_files():
    """Finds README.md, all markdown files in repo root, and all files in docs/."""
    files = []
    # Root markdown files
    for f in os.listdir(REPO_ROOT):
        if f.endswith(".md"):
            files.append(os.path.join(REPO_ROOT, f))
    # docs/ files
    if os.path.isdir(DOCS_DIR):
        for root, _, filenames in os.walk(DOCS_DIR):
            for fn in filenames:
                files.append(os.path.join(root, fn))
    return sorted(files)


class TestAdversarialDocsSanitization(unittest.TestCase):
    """Deep adversarial audit of documentation files."""

    def test_zero_forbidden_names_strict(self):
        """Scans every line of docs with standard case-insensitive regex."""
        doc_files = get_all_doc_files()
        self.assertGreater(len(doc_files), 0, "No doc files found to audit")

        loose_pattern = re.compile(rf"(?i)({'|'.join(FORBIDDEN_NAMES)})")

        violations = []
        for fpath in doc_files:
            rel = os.path.relpath(fpath, REPO_ROOT)
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for line_idx, line in enumerate(f, 1):
                    m = loose_pattern.search(line)
                    if m:
                        violations.append(f"{rel}:{line_idx}: found '{m.group(0)}' in line: {line.strip()[:120]}")

        self.assertEqual(len(violations), 0, f"Found forbidden names in docs:\n" + "\n".join(violations))

    def test_zero_forbidden_names_adversarial_obfuscation(self):
        """Stress-tests for zero-width spaces, soft hyphens, unicode homoglyphs, and punctuation insertion."""
        doc_files = get_all_doc_files()

        violations = []
        for fpath in doc_files:
            rel = os.path.relpath(fpath, REPO_ROOT)
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for line_idx, line in enumerate(f, 1):
                    normalized = unicodedata.normalize("NFKD", line)
                    # Strip non-alphanumeric chars to catch g-e-m-i-n-i or g.e.m.i.n.i
                    stripped = re.sub(r"[^a-zA-Z0-9]", "", normalized.lower())
                    for term in FORBIDDEN_NAMES:
                        if term.lower() in stripped:
                            violations.append(
                                f"{rel}:{line_idx}: obfuscated or normalized match for '{term}' in: {line.strip()[:120]}"
                            )

        self.assertEqual(len(violations), 0, f"Found obfuscated forbidden names in docs:\n" + "\n".join(violations))

    def test_zero_personal_emails_in_docs(self):
        """Scans for personal or real email addresses across all documentation."""
        doc_files = get_all_doc_files()
        email_pattern = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
        allowed_domains = {"example.com", "example.org", "example.net", "apache.org", "w3.org", "android.com"}

        violations = []
        for fpath in doc_files:
            rel = os.path.relpath(fpath, REPO_ROOT)
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for line_idx, line in enumerate(f, 1):
                    for em in FORBIDDEN_EMAIL_LIST:
                        if em.lower() in line.lower():
                            violations.append(f"{rel}:{line_idx}: forbidden target email '{em}'")
                    for m in email_pattern.finditer(line):
                        found_email = m.group(0)
                        domain = found_email.split("@")[-1].lower()
                        if domain not in allowed_domains and not domain.endswith(".example"):
                            violations.append(f"{rel}:{line_idx}: unanonymized email '{found_email}'")

        self.assertEqual(len(violations), 0, f"Found email violations in docs:\n" + "\n".join(violations))

    def test_zero_real_phone_numbers_in_docs(self):
        """Scans for real phone numbers and the forbidden phone number."""
        doc_files = get_all_doc_files()
        phone_10_digit = re.compile(r"(?:\+91[\-\s]?)?([6-9]\d{9})\b")
        allowed_dummies = {"9999999999", "9876543210"}

        violations = []
        for fpath in doc_files:
            rel = os.path.relpath(fpath, REPO_ROOT)
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for line_idx, line in enumerate(f, 1):
                    if TARGET_PHONE in line:
                        violations.append(f"{rel}:{line_idx}: target forbidden phone '{TARGET_PHONE}'")
                    for m in phone_10_digit.finditer(line):
                        num = m.group(1)
                        # Check prefix for +1 dummy (e.g. +15551234567)
                        start_pos = m.start()
                        prefix = line[max(0, start_pos - 2):start_pos]
                        if prefix == "+1" or prefix.endswith("1"):
                            continue
                        if num not in allowed_dummies:
                            violations.append(f"{rel}:{line_idx}: potential real phone '{m.group(0)}'")

        self.assertEqual(len(violations), 0, f"Found phone violations in docs:\n" + "\n".join(violations))

    def test_zero_private_network_ips_in_docs(self):
        """Checks that documentation does not leak private LAN IPs (10/8, 172.16/12, 192.168/16)."""
        doc_files = get_all_doc_files()
        ip_pattern = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")

        violations = []
        for fpath in doc_files:
            rel = os.path.relpath(fpath, REPO_ROOT)
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for line_idx, line in enumerate(f, 1):
                    for m in ip_pattern.finditer(line):
                        ip_str = m.group(1)
                        try:
                            ip_obj = ipaddress.ip_address(ip_str)
                            # Loopback 127.0.0.1 is acceptable for local IPC / port forwarding documentation
                            if ip_obj.is_loopback:
                                continue
                            # RFC 5737 documentation IPs are acceptable (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24)
                            if ip_obj in ipaddress.ip_network("192.0.2.0/24") or \
                               ip_obj in ipaddress.ip_network("198.51.100.0/24") or \
                               ip_obj in ipaddress.ip_network("203.0.113.0/24"):
                                continue
                            # Public DNS like 8.8.8.8 or 1.1.1.1 is acceptable for ping reachability examples
                            if ip_str in {"8.8.8.8", "8.8.4.4", "1.1.1.1", "0.0.0.0"}:
                                continue
                            # If private network IP, flag as violation!
                            if ip_obj.is_private:
                                violations.append(
                                    f"{rel}:{line_idx}: private network IP '{ip_str}' in line: {line.strip()[:100]}"
                                )
                        except ValueError:
                            pass

        self.assertEqual(len(violations), 0, f"Found private network IP violations in docs:\n" + "\n".join(violations))

    def test_sample_env_configs_and_secret_hygiene(self):
        """Ensures all sample environment configs in docs match safe dummy values without live secrets."""
        doc_files = get_all_doc_files()
        secret_prefixes = ("AIza", "gsk_", "sk-or-v1-", "ghp_", "gho_", "Bearer ")

        violations = []
        for fpath in doc_files:
            rel = os.path.relpath(fpath, REPO_ROOT)
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for line_idx, line in enumerate(f, 1):
                    stripped = line.strip()
                    if "=" in stripped and any(k in stripped for k in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
                        k, v = stripped.split("=", 1)
                        v = v.strip().strip("'\"`")
                        for prefix in secret_prefixes:
                            if v.startswith(prefix):
                                violations.append(
                                    f"{rel}:{line_idx}: live key signature '{prefix}' in '{k}={v[:15]}...'"
                                )

        self.assertEqual(len(violations), 0, f"Found live secret signatures in docs:\n" + "\n".join(violations))

    def test_env_example_completeness_and_safety(self):
        """Asserts .env.example exists, contains safe dummy values, and covers all required providers."""
        example_path = os.path.join(REPO_ROOT, ".env.example")
        self.assertTrue(os.path.exists(example_path), ".env.example does not exist")

        with open(example_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        keys_found = {}
        for line_idx, line in enumerate(lines, 1):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                keys_found[k] = v

                # Verify safe dummy value
                self.assertNotIn("AIza", v, f"Line {line_idx}: live key in {k}")
                self.assertNotIn("gsk_", v, f"Line {line_idx}: live key in {k}")
                self.assertNotIn("sk-or-v1-", v, f"Line {line_idx}: live key in {k}")

        # Check required key tiers are represented
        for i in range(1, 8):
            self.assertIn(f"PRIMARY_FLASH_KEY_{i}", keys_found, f"Missing PRIMARY_FLASH_KEY_{i} in .env.example")
        for i in range(1, 6):
            self.assertIn(f"GROQ_API_KEY_{i}", keys_found, f"Missing GROQ_API_KEY_{i} in .env.example")
        for i in range(1, 8):
            self.assertIn(f"OR_KEY_{i}", keys_found, f"Missing OR_KEY_{i} in .env.example")


if __name__ == "__main__":
    unittest.main()
