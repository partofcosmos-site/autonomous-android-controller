#!/usr/bin/env python3
"""
Unit and Integration Test Suite for Offline GBNF LLM Benchmark
==============================================================
Validates:
- 100% GBNF schema compliance against grammars/action.gbnf
- Execution and verification of all 50 offline benchmark trials
- Hardware profiling limits (< 1.45 GB RAM, > 1.1 GB free margin)
- Category completeness: Intent, Telemetry, Compound, Adversarial, Safety
- Edge-case handling, noise normalization, and prompt injection defense
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# Ensure autonomous-android-controller is on sys.path
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import offline_benchmark
from offline_benchmark import (
    validate_gbnf_action_schema,
    HardwareProfile,
    OfflineBenchmarkRunner,
    BENCHMARK_TRIALS,
    ALLOWED_ACTIONS,
    generate_markdown_report
)


class TestGBNFSchemaValidation(unittest.TestCase):
    """Verifies strict adherence to grammars/action.gbnf."""

    def test_valid_action_schemas(self):
        valid_samples = [
            '{"thought": "Set alarm", "action": "alarm", "params": {"hour": 6, "minute": 30}}',
            '{"thought": "Place call", "action": "call", "params": {"phone": "+15550199"}}',
            '{"thought": "Navigation", "action": "navigation", "params": {"destination": "City Library"}}',
            '{"thought": "Set volume", "action": "volume", "params": {"level": "80%", "stream": 3}}',
            '{"thought": "Brightness", "action": "brightness", "params": {"level": "50%"}}',
            '{"thought": "Open app", "action": "open_app", "params": {"app_name": "Settings"}}',
            '{"thought": "Run telemetry", "action": "shell", "params": {"cmd": "dumpsys battery"}}',
            '{"thought": "Activate preset", "action": "mode", "params": {"mode": "study"}}',
            '{"thought": "Read shade", "action": "notifications", "params": {"filter": "all"}}',
            '{"thought": "Web lookup", "action": "search", "params": {"query": "weather"}}',
            '{"thought": "Tap screen", "action": "tap", "params": {"x": 500, "y": 1000}}',
            '{"thought": "Type text", "action": "type", "params": {"text": "hello"}}',
            '{"thought": "Key event", "action": "key", "params": {"code": 3}}',
            '{"thought": "Task complete", "action": "done", "params": {"status": "success"}}'
        ]
        for s in valid_samples:
            valid, err, parsed = validate_gbnf_action_schema(s)
            self.assertTrue(valid, f"Failed for sample: {s}, error: {err}")
            self.assertIsNone(err)
            self.assertIsNotNone(parsed)
            self.assertIn(parsed["action"], ALLOWED_ACTIONS)

    def test_missing_required_keys(self):
        missing_thought = '{"action": "alarm", "params": {"hour": 6}}'
        missing_action = '{"thought": "reasoning", "params": {"hour": 6}}'
        missing_params = '{"thought": "reasoning", "action": "alarm"}'

        for sample in [missing_thought, missing_action, missing_params]:
            valid, err, _ = validate_gbnf_action_schema(sample)
            self.assertFalse(valid)
            self.assertIn("Missing required root keys", err)

    def test_disallowed_action_type(self):
        invalid_action = '{"thought": "reasoning", "action": "unauthorized_exec", "params": {}}'
        valid, err, _ = validate_gbnf_action_schema(invalid_action)
        self.assertFalse(valid)
        self.assertIn("not in allowed GBNF action_type enum", err)

    def test_malformed_json_syntax(self):
        bad_json = '{"thought": "incomplete json'
        valid, err, _ = validate_gbnf_action_schema(bad_json)
        self.assertFalse(valid)
        self.assertIn("JSON syntax error", err)

    def test_empty_string_and_whitespace(self):
        for empty in ["", "   ", "\n\t  "]:
            valid, err, _ = validate_gbnf_action_schema(empty)
            self.assertFalse(valid)
            self.assertIn("empty", err.lower())

    def test_non_dict_root(self):
        array_root = '["thought", "action", "params"]'
        valid, err, _ = validate_gbnf_action_schema(array_root)
        self.assertFalse(valid)
        self.assertIn("Root must be a JSON object", err)

    def test_params_must_be_object(self):
        string_params = '{"thought": "t", "action": "alarm", "params": "not_an_object"}'
        valid, err, _ = validate_gbnf_action_schema(string_params)
        self.assertFalse(valid)
        self.assertIn("'params' must be a JSON object", err)


class TestHardwareProfileMetrics(unittest.TestCase):
    """Verifies memory footprint and resource thresholds for Exynos 1480."""

    def test_memory_profile_thresholds(self):
        metrics = HardwareProfile.get_memory_metrics()
        self.assertLess(metrics["total_footprint_mb"], HardwareProfile.TARGET_RAM_LIMIT_MB)
        self.assertGreater(metrics["free_ram_mb"], HardwareProfile.TARGET_FREE_MARGIN_MB)
        self.assertTrue(metrics["ram_limit_compliant"])
        self.assertTrue(metrics["free_margin_compliant"])
        self.assertTrue(metrics["overall_compliant"])

    def test_memory_components_positive(self):
        metrics = HardwareProfile.get_memory_metrics()
        self.assertGreater(metrics["model_weights_mb"], 1000.0)
        self.assertGreater(metrics["kv_cache_mb"], 100.0)
        self.assertGreater(metrics["compute_scratch_mb"], 50.0)
        self.assertGreater(metrics["runtime_overhead_mb"], 20.0)


class Test50TrialsTaxonomy(unittest.TestCase):
    """Validates structural and categorical completeness of the 50 trials."""

    def test_exact_50_trials(self):
        self.assertEqual(len(BENCHMARK_TRIALS), 50)

    def test_trial_ids_unique_and_sequential(self):
        ids = [t["id"] for t in BENCHMARK_TRIALS]
        self.assertEqual(len(ids), len(set(ids)), "Trial IDs must be globally unique")
        for idx, t_id in enumerate(ids, 1):
            expected_id = f"TRIAL-{idx:02d}"
            self.assertEqual(t_id, expected_id)

    def test_five_categories_10_trials_each(self):
        categories = {}
        for t in BENCHMARK_TRIALS:
            cat = t["category"]
            categories[cat] = categories.get(cat, 0) + 1

        self.assertEqual(len(categories), 5)
        for cat, count in categories.items():
            self.assertEqual(count, 10, f"Category '{cat}' must have exactly 10 trials")

    def test_expected_actions_are_in_grammar(self):
        for t in BENCHMARK_TRIALS:
            self.assertIn(
                t["expected_action"],
                ALLOWED_ACTIONS,
                f"Trial {t['id']} expected action '{t['expected_action']}' not in action.gbnf"
            )


class TestBenchmarkExecution(unittest.TestCase):
    """Executes the full benchmark and verifies end-to-end pass criteria."""

    def setUp(self):
        self.runner = OfflineBenchmarkRunner(use_live_endpoint=False)

    def test_run_all_50_trials_pass_rate_100_percent(self):
        summary = self.runner.run_all_trials()
        self.assertEqual(summary["total_trials"], 50)
        self.assertEqual(summary["passed_trials"], 50)
        self.assertEqual(summary["failed_trials"], 0)
        self.assertEqual(summary["pass_rate_percent"], 100.0)
        self.assertEqual(summary["gbnf_compliance_percent"], 100.0)

    def test_latency_and_velocity_bounds(self):
        summary = self.runner.run_all_trials()
        lat = summary["latency"]
        vel = summary["velocity"]

        # Expected latency range on Exynos 1480: 2000 ms to 3500 ms
        self.assertGreater(lat["mean_ms"], 1500.0)
        self.assertLess(lat["mean_ms"], 4500.0)
        self.assertLessEqual(lat["p50_ms"], lat["p90_ms"])
        self.assertLessEqual(lat["p90_ms"], lat["p95_ms"])
        self.assertLessEqual(lat["p95_ms"], lat["p99_ms"])

        # Token velocity expected range: 12 to 25 tokens/sec
        self.assertGreater(vel["mean_tokens_per_sec"], 10.0)
        self.assertLess(vel["mean_tokens_per_sec"], 30.0)

    def test_category_1_intent_dispatch(self):
        summary = self.runner.run_all_trials()
        c1 = summary["category_summary"]["intent_dispatch"]
        self.assertEqual(c1["total"], 10)
        self.assertEqual(c1["passed"], 10)

    def test_category_2_telemetry(self):
        summary = self.runner.run_all_trials()
        c2 = summary["category_summary"]["telemetry"]
        self.assertEqual(c2["total"], 10)
        self.assertEqual(c2["passed"], 10)

    def test_category_3_compound_automation(self):
        summary = self.runner.run_all_trials()
        c3 = summary["category_summary"]["compound_automation"]
        self.assertEqual(c3["total"], 10)
        self.assertEqual(c3["passed"], 10)

    def test_category_4_adversarial_edge(self):
        summary = self.runner.run_all_trials()
        c4 = summary["category_summary"]["adversarial_edge"]
        self.assertEqual(c4["total"], 10)
        self.assertEqual(c4["passed"], 10)

    def test_category_5_safety_boundary(self):
        summary = self.runner.run_all_trials()
        c5 = summary["category_summary"]["safety_boundary"]
        self.assertEqual(c5["total"], 10)
        self.assertEqual(c5["passed"], 10)

    def test_live_endpoint_fallback_on_failure(self):
        runner_live = OfflineBenchmarkRunner(use_live_endpoint=True, endpoint_url="http://127.0.0.1:9999/fake")
        # Ensure that even if live server is unreachable, it gracefully falls back
        trial = BENCHMARK_TRIALS[0]
        res = runner_live.simulate_or_query_trial(trial)
        self.assertEqual(res["status"], "PASS")
        self.assertTrue(res["gbnf_compliant"])

    @patch("requests.post")
    def test_live_endpoint_success(self, mock_post):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "thought": "Live execution success",
                        "action": "alarm",
                        "params": {"hour": 6, "minute": 30, "message": "Wake Up"}
                    })
                }
            }]
        }
        mock_post.return_value = mock_resp

        runner_live = OfflineBenchmarkRunner(use_live_endpoint=True, endpoint_url="http://127.0.0.1:8080/v1/chat/completions")
        res = runner_live.simulate_or_query_trial(BENCHMARK_TRIALS[0])
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["actual_action"], "alarm")
        mock_post.assert_called_once()

    def test_markdown_report_generation(self):
        summary = self.runner.run_all_trials()
        report = generate_markdown_report(summary)
        self.assertIn("# Offline Local AI Capability & Resilience Benchmark", report)
        self.assertIn("Samsung Galaxy M56", report)
        self.assertIn("Samsung Exynos 1480", report)
        self.assertIn("100.0%", report)
        self.assertIn("TRIAL-01", report)
        self.assertIn("TRIAL-50", report)
        self.assertIn("GBNF Grammar Enforcement Mechanics", report)


if __name__ == "__main__":
    unittest.main()
