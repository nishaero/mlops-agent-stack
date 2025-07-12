#!/usr/bin/env python3
"""
Simplified tests for Infrastructure Healer operator
"""
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Mock kubernetes module to avoid dependency issues
sys.modules["kubernetes"] = MagicMock()
sys.modules["kubernetes.client"] = MagicMock()
sys.modules["kubernetes.client.rest"] = MagicMock()
sys.modules["prometheus_client"] = MagicMock()

from main import ExclusionRules, HealingAction, MonitoringConfig, PodMetrics


class TestBasicFunctionality(unittest.TestCase):
    """Basic functionality tests"""

    def test_pod_metrics_creation(self):
        """Test creating PodMetrics instance"""
        metrics = PodMetrics(
            timestamp=datetime.now(),
            cpu_usage=50.0,
            memory_usage=75.0,
            restart_count=2,
            is_ready=True,
            phase="Running",
        )
        self.assertEqual(metrics.restart_count, 2)
        self.assertTrue(metrics.is_ready)
        self.assertEqual(metrics.phase, "Running")

    def test_healing_action_creation(self):
        """Test creating healing action"""
        action = HealingAction(
            action_type="scale_up",
            target_resource="deployment/test",
            target_namespace="default",
            parameters={"replicas": 3},
            confidence_score=0.8,
        )
        self.assertEqual(action.action_type, "scale_up")
        self.assertEqual(action.confidence_score, 0.8)
        self.assertFalse(action.dry_run)

    def test_exclusion_rules_labels(self):
        """Test exclusion rules with labels"""
        exclusions = ExclusionRules(labels={"mlops.ai/exclude": "true"})

        # Should match exclusion label
        self.assertTrue(exclusions.matches_labels({"mlops.ai/exclude": "true", "app": "web"}))

        # Should not match different values
        self.assertFalse(exclusions.matches_labels({"mlops.ai/exclude": "false"}))
        self.assertFalse(exclusions.matches_labels({"app": "web"}))

    def test_exclusion_rules_namespaces(self):
        """Test exclusion rules with namespaces"""
        exclusions = ExclusionRules(namespaces={"kube-system", "monitoring"})

        # Should match excluded namespaces
        self.assertTrue(exclusions.matches_namespace("kube-system"))
        self.assertTrue(exclusions.matches_namespace("monitoring"))

        # Should not match other namespaces
        self.assertFalse(exclusions.matches_namespace("default"))
        self.assertFalse(exclusions.matches_namespace("production"))

    def test_monitoring_config_basic(self):
        """Test basic monitoring configuration"""
        config = MonitoringConfig(namespaces=["default", "production"])

        # Should monitor specified namespaces
        self.assertTrue(config.should_monitor_namespace("default"))
        self.assertTrue(config.should_monitor_namespace("production"))

        # Should not monitor unspecified namespaces
        self.assertFalse(config.should_monitor_namespace("staging"))


if __name__ == "__main__":
    unittest.main()
