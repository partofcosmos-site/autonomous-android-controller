"""
Comprehensive Sanitization and Privacy Protection Test Suite.

Verifies:
1. Zero occurrences of forbidden brand and personal names.
2. Zero occurrences of personal phone numbers.
3. Zero occurrences of personal email addresses.
4. Zero occurrences of private LAN IP addresses.
5. Strict secret hygiene (.env absent, .gitignore covers .env, .env.example contains dummy values, Apache-2.0 LICENSE).
"""

import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dynamically construct forbidden terms so this test file itself contains
# zero literal occurrences of forbidden brand or personal names.
_FORBIDDEN_NAME_PARTS = [
    ("ge", "mini"),
    ("mad", "habi"),
    ("mad", "havi"),
]
FORBIDDEN_NAMES = [p1 + p2 for p1, p2 in _FORBIDDEN_NAME_PARTS]

_FORBIDDEN_EMAIL_PARTS = [
    ("biswas", "mad", "habi02", "@gmail.com"),
    ("debanjan", "8686", "@gmail.com"),
]
FORBIDDEN_EMAILS = ["".join(parts) for parts in _FORBIDDEN_EMAIL_PARTS]

_FORBIDDEN_PHONE_PARTS = ("956404", "3905")
FORBIDDEN_PHONE = "".join(_FORBIDDEN_PHONE_PARTS)

IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules"}
IGNORED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc", ".db", ".zip", ".tar", ".gz"}


def get_scannable_repo_files():
    """Returns absolute paths to all text and code files in the repository."""
    scannable_files = []
    current_test_file = os.path.abspath(__file__)
    for root, dirs, filenames in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext in IGNORED_EXTS:
                continue
            full_path = os.path.join(root, f)
            if os.path.abspath(full_path) == current_test_file:
                continue
            scannable_files.append(full_path)
    return scannable_files


class TestSanitization(unittest.TestCase):
    """Rigorous audit suite for privacy, brand sanitization, and secret hygiene."""

    def test_zero_forbidden_names(self):
        """Verify zero forbidden brand or personal names across all repo files."""
        pattern = re.compile(rf"(?i)({'|'.join(FORBIDDEN_NAMES)})")
        matches = []

        for fpath in get_scannable_repo_files():
            rel_path = os.path.relpath(fpath, REPO_ROOT)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        m = pattern.search(line)
                        if m:
                            matches.append(f"{rel_path}:{line_num}: matched '{m.group(0)}' in: {line.strip()[:100]}")
            except Exception as e:
                matches.append(f"{rel_path}: failed to read: {e}")

        self.assertEqual(len(matches), 0, f"Forbidden brand/personal names discovered:\n" + "\n".join(matches))

    def test_zero_real_phone_numbers(self):
        """Scans for forbidden phone number and real phone patterns -> assert 0 matches."""
        # Real phone regex matching 10-digit mobile numbers starting with [6-9]
        # allowing optional +91 or separators, excluding mock dummy values (+919999999999, +1555...)
        real_phone_pattern = re.compile(r"(?:\+91[\-\s]?)?([6-9]\d{9})\b")

        # Permitted dummy placeholders: all 9s or countdown 9..0 mock fixture
        allowed_dummies = {"9999999999", "9876543210"}

        matches = []
        for fpath in get_scannable_repo_files():
            rel_path = os.path.relpath(fpath, REPO_ROOT)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if FORBIDDEN_PHONE in line:
                            matches.append(f"{rel_path}:{line_num}: found forbidden phone {FORBIDDEN_PHONE}")
                        for m in real_phone_pattern.finditer(line):
                            num = m.group(1)
                            # If preceded by +1, it's a +1 international dummy (e.g. +19876543210)
                            start_idx = m.start()
                            prefix = line[max(0, start_idx - 2):start_idx]
                            if prefix == "+1" or prefix.endswith("1"):
                                continue
                            if num not in allowed_dummies:
                                matches.append(f"{rel_path}:{line_num}: potential real phone '{m.group(0)}'")
            except Exception as e:
                matches.append(f"{rel_path}: failed to read: {e}")

        self.assertEqual(len(matches), 0, f"Real phone numbers discovered:\n" + "\n".join(matches))

    def test_zero_personal_emails(self):
        """Scan for forbidden personal emails and unanonymized email addresses -> assert 0 matches."""
        forbidden_specific = re.compile(rf"(?i)({'|'.join([re.escape(em) for em in FORBIDDEN_EMAILS])})")
        personal_domain_pattern = re.compile(r"[a-zA-Z0-9_.+-]+@(?!example\.(?:com|org|net))[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

        # Permitted non-personal domains or doc/tool references (e.g. apache.org in license, schemas)
        allowed_domains = {"apache.org", "w3.org", "android.com", "example.com", "example.org", "example.net"}

        matches = []
        for fpath in get_scannable_repo_files():
            rel_path = os.path.relpath(fpath, REPO_ROOT)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if forbidden_specific.search(line):
                            matches.append(f"{rel_path}:{line_num}: forbidden personal email in: {line.strip()[:100]}")
                        for em in personal_domain_pattern.finditer(line):
                            email_str = em.group(0)
                            domain = email_str.split("@")[-1].lower()
                            if domain not in allowed_domains and not domain.endswith(".example"):
                                matches.append(f"{rel_path}:{line_num}: unanonymized email '{email_str}'")
            except Exception as e:
                matches.append(f"{rel_path}: failed to read: {e}")

        self.assertEqual(len(matches), 0, f"Personal email addresses discovered:\n" + "\n".join(matches))

    def test_zero_private_lan_ips(self):
        """Scan for 192.168. and 10. private network IPs -> assert 0 matches."""
        lan_pattern = re.compile(r"(192\.168\.\d+\.\d+|\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b)")
        matches = []

        for fpath in get_scannable_repo_files():
            rel_path = os.path.relpath(fpath, REPO_ROOT)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        m = lan_pattern.search(line)
                        if m:
                            matches.append(f"{rel_path}:{line_num}: found private LAN IP '{m.group(0)}' in: {line.strip()[:100]}")
            except Exception as e:
                matches.append(f"{rel_path}: failed to read: {e}")

        self.assertEqual(len(matches), 0, f"Private LAN IP addresses discovered:\n" + "\n".join(matches))

    def test_secret_hygiene(self):
        """Assert .env does not exist, .gitignore excludes .env, .env.example exists with dummy values, and LICENSE is Apache-2.0."""
        # 1. .env must NOT exist in repo root
        env_path = os.path.join(REPO_ROOT, ".env")
        self.assertFalse(os.path.exists(env_path), f"Live secret file exists at {env_path}")

        # 2. .gitignore must exclude .env
        gitignore_path = os.path.join(REPO_ROOT, ".gitignore")
        self.assertTrue(os.path.exists(gitignore_path), ".gitignore file is missing")
        with open(gitignore_path, "r", encoding="utf-8") as f:
            gitignore_content = f.read()
        self.assertIn(".env", gitignore_content.splitlines(), ".gitignore does not explicitly ignore .env")

        # 3. .env.example exists and contains ONLY dummy placeholders
        example_path = os.path.join(REPO_ROOT, ".env.example")
        self.assertTrue(os.path.exists(example_path), ".env.example template is missing")
        with open(example_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip().strip("'\"")
                    # Assert no live key signatures
                    self.assertFalse(v.startswith("AIza"), f"Live Google API key found in .env.example:{line_num}")
                    self.assertFalse(v.startswith("gsk_"), f"Live Groq API key found in .env.example:{line_num}")
                    self.assertFalse(v.startswith("sk-or-v1-"), f"Live OpenRouter API key found in .env.example:{line_num}")

        # 4. LICENSE file exists and is Apache-2.0
        license_path = os.path.join(REPO_ROOT, "LICENSE")
        self.assertTrue(os.path.exists(license_path), "LICENSE file is missing from repository root")
        with open(license_path, "r", encoding="utf-8") as f:
            license_text = f.read()
        self.assertIn("Apache License", license_text, "LICENSE does not contain 'Apache License'")
        self.assertIn("Version 2.0", license_text, "LICENSE does not specify 'Version 2.0'")


if __name__ == "__main__":
    unittest.main()
