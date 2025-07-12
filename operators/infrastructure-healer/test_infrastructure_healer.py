#!/usr/bin/env python3
"""
Tests for Infrastructure Healer operator with observation-based healing
"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Mock kubernetes module to avoid dependency issues
sys.modules["kubernetes"] = MagicMock()
sys.modules["kubernetes.client"] = MagicMock()
sys.modules["kubernetes.client.rest"] = MagicMock()
sys.modules["prometheus_client"] = MagicMock()

from main import (
    ActionPlanner,
    HealingAction,
    ObservationWindow,
    PodMetrics,
    PodObserver,
)


class TestPodMetrics(unittest.TestCase):
    """Test PodMetrics data class"""

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


class TestObservationWindow(unittest.TestCase):
    """Test ObservationWindow functionality"""

    def setUp(self):
        self.window = ObservationWindow("test/pod")

    def test_add_metric(self):
        """Test adding metrics to observation window"""
        metric = PodMetrics(timestamp=datetime.now(), restart_count=1)
        self.window.add_metric(metric)
        self.assertEqual(len(self.window.metrics), 1)

    def test_get_trend_insufficient_data(self):
        """Test trend calculation with insufficient data"""
        slope, confidence = self.window.get_trend("restart_count")
        self.assertEqual(slope, 0.0)
        self.assertEqual(confidence, 0.0)

    def test_get_trend_with_data(self):
        """Test trend calculation with sufficient data"""
        base_time = datetime.now()

        # Add metrics with increasing restart count
        for i in range(5):
            metric = PodMetrics(
                timestamp=base_time + timedelta(minutes=i), restart_count=i
            )
            self.window.add_metric(metric)

        slope, confidence = self.window.get_trend("restart_count", window_minutes=10)
        self.assertGreater(slope, 0)  # Should show upward trend
        self.assertGreater(confidence, 0)

    def test_cooldown_check(self):
        """Test cooldown period functionality"""
        # No action time - not in cooldown
        self.assertFalse(self.window.is_in_cooldown())

        # Recent action time - in cooldown
        self.window.last_action_time = datetime.now() - timedelta(minutes=2)
        self.assertTrue(self.window.is_in_cooldown())

        # Old action time - not in cooldown
        self.window.last_action_time = datetime.now() - timedelta(minutes=10)
        self.assertFalse(self.window.is_in_cooldown())

    def test_stability_score(self):
        """Test stability score calculation"""
        base_time = datetime.now()

        # Add stable metrics
        for i in range(5):
            metric = PodMetrics(
                timestamp=base_time + timedelta(minutes=i),
                restart_count=0,
                is_ready=True,
            )
            self.window.add_metric(metric)

        score = self.window.get_stability_score()
        self.assertGreater(score, 0.8)  # Should be high stability


class TestPodObserver(unittest.TestCase):
    """Test PodObserver functionality"""

    def setUp(self):
        self.observer = PodObserver()

    def test_resource_key_generation(self):
        """Test resource key generation"""
        key = self.observer.get_resource_key("default", "test-pod")
        self.assertEqual(key, "default/test-pod")

    def test_cleanup_old_observations(self):
        """Test cleanup of old observation data"""
        # Add old observation
        old_window = ObservationWindow("test/old-pod")
        old_metric = PodMetrics(
            timestamp=datetime.now() - timedelta(hours=25), restart_count=1
        )
        old_window.add_metric(old_metric)
        self.observer.observations["test/old-pod"] = old_window

        # Add recent observation
        new_window = ObservationWindow("test/new-pod")
        new_metric = PodMetrics(timestamp=datetime.now(), restart_count=1)
        new_window.add_metric(new_metric)
        self.observer.observations["test/new-pod"] = new_window

        # Cleanup should remove old observation
        self.observer.cleanup_old_observations(max_age_hours=24)

        self.assertNotIn("test/old-pod", self.observer.observations)
        self.assertIn("test/new-pod", self.observer.observations)


class TestActionPlanner(unittest.TestCase):
    """Test ActionPlanner functionality"""

    def setUp(self):
        self.observer = PodObserver()
        self.planner = ActionPlanner(self.observer)

    def test_calculate_scaling_confidence(self):
        """Test scaling confidence calculation"""
        confidence = self.planner.calculate_scaling_confidence(
            "test-deployment", "default", 2, 4
        )
        self.assertGreaterEqual(confidence, 0.1)
        self.assertLessEqual(confidence, 1.0)

    def test_calculate_restart_confidence(self):
        """Test restart confidence calculation"""
        confidence = self.planner.calculate_restart_confidence("test-pod", "default")
        self.assertGreaterEqual(confidence, 0.1)
        self.assertLessEqual(confidence, 1.0)

    def test_pending_actions_management(self):
        """Test pending actions management"""
        action = HealingAction(
            action_type="scale_up",
            target_resource="deployment/test",
            target_namespace="default",
            parameters={"replicas": 3},
            confidence_score=0.8,
            observation_period=timedelta(seconds=1),  # Short for testing
        )

        self.planner.add_pending_action(action)
        self.assertEqual(len(self.planner.pending_actions), 1)

        # Should not be ready immediately
        ready_actions = self.planner.get_ready_actions()
        self.assertEqual(len(ready_actions), 0)


class TestHealingAction(unittest.TestCase):
    """Test HealingAction functionality"""

    def test_action_creation(self):
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

    def test_ready_to_execute(self):
        """Test action readiness checking"""
        # Action with short observation period
        action = HealingAction(
            action_type="scale_up",
            target_resource="deployment/test",
            target_namespace="default",
            parameters={"replicas": 3},
            observation_period=timedelta(seconds=1),
        )

        # Should not be ready immediately after creation
        self.assertFalse(action.is_ready_to_execute())


if __name__ == "__main__":
    unittest.main()
