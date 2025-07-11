#!/usr/bin/env python3
"""
Infrastructure Healer for MLOps Agent Stack

This component handles:
- Pod and node scaling based on healing rules
- Automatic rollbacks for failed deployments
- Resource optimization and adjustment
- Integration with Cluster API for cloud-agnostic scaling
"""

import asyncio
import logging
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from statistics import mean, median

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Metrics
HEALING_ACTIONS = Counter(
    "mlops_healing_actions_total", "Total healing actions taken", ["type", "result"]
)
HEALING_DURATION = Histogram(
    "mlops_healing_duration_seconds", "Time spent on healing actions", ["action_type"]
)
ACTIVE_RULES = Gauge("mlops_active_healing_rules", "Number of active healing rules")
OBSERVATION_DURATION = Histogram(
    "mlops_observation_duration_seconds", "Time spent observing before action", ["resource_type"]
)
CONFIDENCE_SCORE = Gauge(
    "mlops_action_confidence", "Confidence score for healing actions", ["action_type"]
)

logger = logging.getLogger(__name__)


@dataclass
class PodMetrics:
    """Pod performance metrics over time"""
    timestamp: datetime
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    restart_count: int = 0
    is_ready: bool = True
    phase: str = "Running"
    oom_killed: bool = False


@dataclass
class ObservationWindow:
    """Rolling window of observations for a resource"""
    resource_key: str
    metrics: deque = field(default_factory=lambda: deque(maxlen=100))
    last_action_time: Optional[datetime] = None
    cooldown_period: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    
    def add_metric(self, metric: PodMetrics) -> None:
        """Add a new metric to the observation window"""
        self.metrics.append(metric)
    
    def get_trend(self, metric_name: str, window_minutes: int = 10) -> Tuple[float, float]:
        """Get trend analysis for a specific metric"""
        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        recent_metrics = [m for m in self.metrics if m.timestamp >= cutoff_time]
        
        if len(recent_metrics) < 2:
            return 0.0, 0.0  # slope, confidence
        
        values = [getattr(m, metric_name) for m in recent_metrics]
        times = [(m.timestamp - recent_metrics[0].timestamp).total_seconds() 
                for m in recent_metrics]
        
        # Simple linear regression for trend
        n = len(values)
        sum_x = sum(times)
        sum_y = sum(values)
        sum_xy = sum(x * y for x, y in zip(times, values))
        sum_x2 = sum(x * x for x in times)
        
        if n * sum_x2 - sum_x * sum_x == 0:
            return 0.0, 0.0
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        confidence = min(1.0, len(recent_metrics) / 10.0)  # More data = higher confidence
        
        return slope, confidence
    
    def is_in_cooldown(self) -> bool:
        """Check if resource is in cooldown period"""
        if not self.last_action_time:
            return False
        return datetime.now() - self.last_action_time < self.cooldown_period
    
    def get_stability_score(self) -> float:
        """Calculate stability score based on recent metrics"""
        if len(self.metrics) < 5:
            return 0.5  # Neutral score for insufficient data
        
        recent_metrics = list(self.metrics)[-10:]  # Last 10 observations
        
        # Calculate variability in key metrics
        restart_counts = [m.restart_count for m in recent_metrics]
        ready_states = [m.is_ready for m in recent_metrics]
        
        restart_stability = 1.0 if len(set(restart_counts)) <= 1 else 0.5
        ready_stability = sum(ready_states) / len(ready_states)
        
        return (restart_stability + ready_stability) / 2


@dataclass
class HealingAction:
    """Represents a healing action to be taken"""

    action_type: str  # scale_up, scale_down, restart, rollback
    target_resource: str
    target_namespace: str
    parameters: Dict[str, Any]
    priority: int = 1  # 1=low, 2=medium, 3=high, 4=critical
    dry_run: bool = False
    confidence_score: float = 0.0
    observation_period: timedelta = field(default_factory=lambda: timedelta(minutes=3))
    created_at: datetime = field(default_factory=datetime.now)
    
    def is_ready_to_execute(self) -> bool:
        """Check if action has been observed long enough"""
        return datetime.now() - self.created_at >= self.observation_period


class PodObserver:
    """Observes and tracks pod performance over time"""
    
    def __init__(self):
        self.observations: Dict[str, ObservationWindow] = {}
        self.min_observation_period = timedelta(minutes=2)
    
    def get_resource_key(self, namespace: str, name: str) -> str:
        """Generate unique key for resource"""
        return f"{namespace}/{name}"
    
    async def observe_pod(self, pod, namespace: str) -> PodMetrics:
        """Collect current metrics for a pod"""
        try:
            metrics = PodMetrics(
                timestamp=datetime.now(),
                restart_count=sum(
                    container.restart_count or 0
                    for container in pod.status.container_statuses or []
                ),
                is_ready=(pod.status.phase == "Running"),
                phase=pod.status.phase,
                oom_killed=any(
                    container.last_state
                    and container.last_state.terminated
                    and container.last_state.terminated.reason == "OOMKilled"
                    for container in pod.status.container_statuses or []
                )
            )
            
            # Store observation
            resource_key = self.get_resource_key(namespace, pod.metadata.name)
            if resource_key not in self.observations:
                self.observations[resource_key] = ObservationWindow(resource_key)
            
            self.observations[resource_key].add_metric(metrics)
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to observe pod {pod.metadata.name}: {e}")
            return PodMetrics(timestamp=datetime.now())
    
    def get_observation_window(self, namespace: str, name: str) -> Optional[ObservationWindow]:
        """Get observation window for a resource"""
        resource_key = self.get_resource_key(namespace, name)
        return self.observations.get(resource_key)
    
    def cleanup_old_observations(self, max_age_hours: int = 24) -> None:
        """Clean up old observation data"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        for window in self.observations.values():
            # Remove old metrics
            while window.metrics and window.metrics[0].timestamp < cutoff_time:
                window.metrics.popleft()
        
        # Remove empty windows
        empty_keys = [
            key for key, window in self.observations.items() 
            if not window.metrics
        ]
        for key in empty_keys:
            del self.observations[key]


class ActionPlanner:
    """Plans and scores healing actions based on observations"""
    
    def __init__(self, observer: PodObserver):
        self.observer = observer
        self.pending_actions: List[HealingAction] = []
    
    def calculate_scaling_confidence(self, deployment_name: str, namespace: str, 
                                   current_replicas: int, target_replicas: int) -> float:
        """Calculate confidence score for scaling action"""
        confidence = 0.5  # Base confidence
        
        # Get pods for this deployment
        pods_pattern = f"{namespace}/{deployment_name}-"
        related_windows = [
            window for key, window in self.observer.observations.items()
            if key.startswith(pods_pattern)
        ]
        
        if not related_windows:
            return confidence
        
        # Analyze stability across pods
        stability_scores = [window.get_stability_score() for window in related_windows]
        avg_stability = mean(stability_scores) if stability_scores else 0.5
        
        # Analyze trends
        trend_scores = []
        for window in related_windows:
            restart_trend, trend_confidence = window.get_trend('restart_count')
            if trend_confidence > 0.5:
                # Increasing restarts = lower confidence in scaling down
                if target_replicas < current_replicas and restart_trend > 0:
                    trend_scores.append(0.3)
                elif target_replicas > current_replicas and restart_trend > 0:
                    trend_scores.append(0.8)
                else:
                    trend_scores.append(0.6)
        
        avg_trend_score = mean(trend_scores) if trend_scores else 0.5
        
        # Calculate final confidence
        confidence = (avg_stability * 0.6 + avg_trend_score * 0.4)
        
        # Penalize large scaling changes
        scale_factor = abs(target_replicas - current_replicas) / current_replicas
        if scale_factor > 1.0:  # More than 100% change
            confidence *= 0.7
        
        return min(1.0, max(0.1, confidence))
    
    def calculate_restart_confidence(self, pod_name: str, namespace: str) -> float:
        """Calculate confidence score for pod restart action"""
        window = self.observer.get_observation_window(namespace, pod_name)
        if not window:
            return 0.3  # Low confidence without observations
        
        if len(window.metrics) < 3:
            return 0.4  # Low confidence with few observations
        
        # Check if restart count is consistently increasing
        recent_metrics = list(window.metrics)[-5:]
        restart_counts = [m.restart_count for m in recent_metrics]
        
        if len(set(restart_counts)) == 1:
            return 0.2  # No restart pattern, low confidence
        
        # Check for consistent restart pattern
        if restart_counts[-1] > restart_counts[0]:
            return 0.8  # Clear restart pattern
        
        return 0.5
    
    def should_take_action(self, action: HealingAction) -> bool:
        """Determine if an action should be taken based on confidence and cooldown"""
        # Check cooldown period
        if action.action_type.startswith('scale'):
            deployment_name = action.target_resource.split('/')[-1]
            # Check if any pods from this deployment are in cooldown
            pods_pattern = f"{action.target_namespace}/{deployment_name}-"
            for key, window in self.observer.observations.items():
                if key.startswith(pods_pattern) and window.is_in_cooldown():
                    return False
        
        # Check confidence threshold
        min_confidence = {
            'scale_up': 0.6,
            'scale_down': 0.7,  # Higher threshold for scale down
            'restart_pod': 0.5,
            'increase_memory': 0.6,
            'rollback': 0.8
        }.get(action.action_type, 0.6)
        
        return action.confidence_score >= min_confidence
    
    def add_pending_action(self, action: HealingAction) -> None:
        """Add action to pending list for observation"""
        self.pending_actions.append(action)
    
    def get_ready_actions(self) -> List[HealingAction]:
        """Get actions that are ready to execute"""
        ready_actions = []
        remaining_actions = []
        
        for action in self.pending_actions:
            if action.is_ready_to_execute() and self.should_take_action(action):
                ready_actions.append(action)
            elif not action.is_ready_to_execute():
                remaining_actions.append(action)
            # Drop actions that don't meet confidence threshold
        
        self.pending_actions = remaining_actions
        return ready_actions


class InfrastructureHealer:
    """Main Infrastructure Healing Controller with observation-based decision making"""

    def __init__(self):
        self.reconcile_interval = int(os.getenv("RECONCILE_INTERVAL", "30"))
        self.dry_run_mode = os.getenv("DRY_RUN", "false").lower() == "true"
        self.observation_enabled = os.getenv("OBSERVATION_MODE", "true").lower() == "true"

        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()

        self.k8s_client = client.ApiClient()
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.autoscaling_v1 = client.AutoscalingV1Api()
        self.custom_api = client.CustomObjectsApi()

        # Enhanced healing components
        self.observer = PodObserver()
        self.action_planner = ActionPlanner(self.observer)
        self.active_rules = {}
        self.action_history = []
        self.last_actions = {}
        
        # Performance tracking
        self.deployment_cache = {}
        self.last_cache_update = datetime.now()

    async def get_healing_rules(self) -> List[Dict]:
        """Get all InfraHealingRule resources with caching"""
        try:
            rules = await self.custom_api.list_cluster_custom_object(
                group="mlops.ai", version="v1", plural="infrahealingrules"
            )
            return rules.get("items", [])
        except ApiException as e:
            if e.status != 404:
                logger.error(f"Failed to get healing rules: {e}")
            return []

    async def update_deployment_cache(self, namespace: str) -> None:
        """Update cached deployment information for efficiency"""
        try:
            if namespace not in self.deployment_cache:
                self.deployment_cache[namespace] = {}
            
            deployments = await self.apps_v1.list_namespaced_deployment(namespace=namespace)
            for deployment in deployments.items:
                self.deployment_cache[namespace][deployment.metadata.name] = {
                    'replicas': deployment.spec.replicas or 1,
                    'ready_replicas': deployment.status.ready_replicas or 0,
                    'updated_at': datetime.now()
                }
        except ApiException as e:
            logger.error(f"Failed to update deployment cache for {namespace}: {e}")

    async def observe_and_analyze_pods(self, namespace: str, label_selector: str) -> Dict[str, Any]:
        """Observe pods and analyze their performance trends"""
        try:
            pods = await self.core_v1.list_namespaced_pod(
                namespace=namespace, label_selector=label_selector
            )
            
            pod_analysis = {
                'total_pods': len(pods.items),
                'unhealthy_pods': 0,
                'restart_trends': [],
                'stability_scores': [],
                'pods_ready': 0
            }
            
            for pod in pods.items:
                # Observe each pod
                metrics = await self.observer.observe_pod(pod, namespace)
                window = self.observer.get_observation_window(namespace, pod.metadata.name)
                
                # Analyze pod health
                if not metrics.is_ready or metrics.restart_count > 3:
                    pod_analysis['unhealthy_pods'] += 1
                else:
                    pod_analysis['pods_ready'] += 1
                
                # Get trend analysis if we have enough data
                if window and len(window.metrics) >= 3:
                    restart_trend, confidence = window.get_trend('restart_count')
                    stability = window.get_stability_score()
                    
                    pod_analysis['restart_trends'].append({
                        'pod': pod.metadata.name,
                        'trend': restart_trend,
                        'confidence': confidence
                    })
                    pod_analysis['stability_scores'].append(stability)
            
            return pod_analysis
            
        except ApiException as e:
            logger.error(f"Failed to observe pods in {namespace}: {e}")
            return {'total_pods': 0, 'unhealthy_pods': 0, 'restart_trends': [], 'stability_scores': [], 'pods_ready': 0}

    async def evaluate_pod_scaling(self, rule: Dict) -> List[HealingAction]:
        """Evaluate if pod scaling is needed based on observed metrics and trends"""
        actions: List[HealingAction] = []
        spec = rule.get("spec", {})
        scaling_config = spec.get("scaling", {}).get("pods", {})

        if not scaling_config.get("enabled", False):
            return actions

        scope = spec.get("scope", {})
        namespaces = scope.get("namespaces", ["default"])
        label_selector = self.build_label_selector(scope.get("labels", {}))

        for namespace in namespaces:
            try:
                # Update cache for efficiency
                await self.update_deployment_cache(namespace)
                
                # Observe and analyze pod performance
                pod_analysis = await self.observe_and_analyze_pods(namespace, label_selector)
                
                # Get deployments in namespace
                deployments = await self.apps_v1.list_namespaced_deployment(
                    namespace=namespace, label_selector=label_selector
                )

                for deployment in deployments.items:
                    action = await self.evaluate_deployment_scaling_with_observation(
                        deployment, scaling_config, rule, pod_analysis
                    )
                    if action:
                        actions.append(action)

            except ApiException as e:
                logger.error(f"Failed to list deployments in {namespace}: {e}")

        return actions

    async def evaluate_deployment_scaling_with_observation(
        self, deployment, scaling_config: Dict, rule: Dict, pod_analysis: Dict
    ) -> Optional[HealingAction]:
        """Evaluate scaling for a specific deployment using observation data"""
        try:
            name = deployment.metadata.name
            namespace = deployment.metadata.namespace
            current_replicas = deployment.spec.replicas or 1
            ready_replicas = deployment.status.ready_replicas or 0
            
            # Calculate health ratio from observations
            unhealthy_ratio = 0.0
            if pod_analysis['total_pods'] > 0:
                unhealthy_ratio = pod_analysis['unhealthy_pods'] / pod_analysis['total_pods']
            
            # Analyze trends for more intelligent decisions
            avg_stability = 0.5
            if pod_analysis['stability_scores']:
                avg_stability = mean(pod_analysis['stability_scores'])
            
            # Get scaling parameters
            max_replicas = scaling_config.get("maxReplicas", 10)
            min_replicas = scaling_config.get("minReplicas", 1)
            scale_up_threshold = float(scaling_config.get("scaleUpThreshold", "75%").rstrip('%')) / 100
            scale_down_threshold = float(scaling_config.get("scaleDownThreshold", "25%").rstrip('%')) / 100
            
            target_replicas = current_replicas
            action_type = None
            observation_period = timedelta(minutes=3)
            
            # More conservative scaling based on observations
            if unhealthy_ratio > scale_up_threshold and current_replicas < max_replicas:
                # Scale up gradually - don't double replicas immediately
                if avg_stability < 0.6:  # Low stability = more conservative scaling
                    target_replicas = current_replicas + 1
                else:
                    target_replicas = min(current_replicas + max(1, current_replicas // 2), max_replicas)
                action_type = "scale_up"
                observation_period = timedelta(minutes=2)  # Faster for urgent scale up
                
            elif unhealthy_ratio < scale_down_threshold and current_replicas > min_replicas:
                # Scale down only if stability is high
                if avg_stability > 0.7 and ready_replicas == current_replicas:
                    target_replicas = max(current_replicas - 1, min_replicas)
                    action_type = "scale_down"
                    observation_period = timedelta(minutes=5)  # Longer observation for scale down

            if action_type and target_replicas != current_replicas:
                # Calculate confidence score
                confidence = self.action_planner.calculate_scaling_confidence(
                    name, namespace, current_replicas, target_replicas
                )
                
                action = HealingAction(
                    action_type=action_type,
                    target_resource=f"deployment/{name}",
                    target_namespace=namespace,
                    parameters={
                        "replicas": target_replicas,
                        "current_replicas": current_replicas,
                        "unhealthy_ratio": unhealthy_ratio,
                        "stability_score": avg_stability,
                        "ready_replicas": ready_replicas,
                    },
                    priority=3 if action_type == "scale_up" else 2,
                    confidence_score=confidence,
                    observation_period=observation_period,
                    dry_run=rule.get("spec", {})
                    .get("safeguards", {})
                    .get("dryRun", False),
                )
                
                # Record confidence score metric
                CONFIDENCE_SCORE.labels(action_type=action_type).set(confidence)
                
                return action

        except Exception as e:
            logger.error(
                f"Failed to evaluate deployment scaling for {deployment.metadata.name}: {e}"
            )

        return None

    async def evaluate_pod_health(self, rule: Dict) -> List[HealingAction]:
        """Evaluate pod health and generate healing actions with observation"""
        actions = []
        spec = rule.get("spec", {})
        health_config = spec.get("healthChecks", {}).get("pods", {})
        scope = spec.get("scope", {})

        namespaces = scope.get("namespaces", ["default"])
        label_selector = self.build_label_selector(scope.get("labels", {}))

        for namespace in namespaces:
            try:
                pods = await self.core_v1.list_namespaced_pod(
                    namespace=namespace, label_selector=label_selector
                )

                for pod in pods.items:
                    # First observe the pod to collect metrics
                    await self.observer.observe_pod(pod, namespace)
                    
                    action = await self.evaluate_single_pod_health_with_observation(
                        pod, health_config, rule
                    )
                    if action:
                        actions.append(action)

            except ApiException as e:
                logger.error(f"Failed to list pods in {namespace}: {e}")

        return actions

    async def evaluate_single_pod_health_with_observation(
        self, pod, health_config: Dict, rule: Dict
    ) -> Optional[HealingAction]:
        """Evaluate health of a single pod using observation data"""
        try:
            name = pod.metadata.name
            namespace = pod.metadata.namespace
            
            # Get observation window for this pod
            window = self.observer.get_observation_window(namespace, name)
            
            # Check restart count with trend analysis
            restart_threshold = health_config.get("restartThreshold", 5)
            max_restart_count = 0

            for container in pod.status.container_statuses or []:
                restart_count = container.restart_count or 0
                max_restart_count = max(max_restart_count, restart_count)

            # Use observation data to make smarter decisions
            if max_restart_count > restart_threshold:
                # Check if restart count is trending upward
                should_restart = True
                observation_period = timedelta(minutes=3)
                
                if window and len(window.metrics) >= 3:
                    restart_trend, trend_confidence = window.get_trend('restart_count')
                    stability_score = window.get_stability_score()
                    
                    # Only restart if there's a clear upward trend in restarts
                    if restart_trend <= 0 or trend_confidence < 0.5:
                        should_restart = False
                    elif stability_score > 0.7:  # High stability = maybe transient issue
                        observation_period = timedelta(minutes=5)  # Wait longer
                
                if should_restart:
                    action_type = health_config.get("crashLoopBackoffAction", "restart")
                    
                    if action_type == "restart":
                        confidence = self.action_planner.calculate_restart_confidence(name, namespace)
                        
                        return HealingAction(
                            action_type="restart_pod",
                            target_resource=f"pod/{name}",
                            target_namespace=namespace,
                            parameters={
                                "restart_count": max_restart_count,
                                "threshold": restart_threshold,
                                "restart_trend": restart_trend if window else 0,
                            },
                            priority=3,
                            confidence_score=confidence,
                            observation_period=observation_period,
                            dry_run=rule.get("spec", {})
                            .get("safeguards", {})
                            .get("dryRun", False),
                        )

            # Check for OOMKilled containers with observation
            for container in pod.status.container_statuses or []:
                if (
                    container.last_state
                    and container.last_state.terminated
                    and container.last_state.terminated.reason == "OOMKilled"
                ):
                    # Check if this is a pattern or one-off event
                    oom_confidence = 0.8  # Default high confidence for OOM
                    observation_period = timedelta(minutes=2)
                    
                    if window and len(window.metrics) >= 2:
                        # Check recent OOM events
                        recent_ooms = sum(1 for m in list(window.metrics)[-5:] if m.oom_killed)
                        if recent_ooms <= 1:  # Only one recent OOM
                            oom_confidence = 0.6
                            observation_period = timedelta(minutes=4)

                    action_type = health_config.get("oomKilledAction", "increase-memory")

                    if action_type == "increase-memory":
                        return HealingAction(
                            action_type="increase_memory",
                            target_resource=f"pod/{name}",
                            target_namespace=namespace,
                            parameters={
                                "container": container.name,
                                "reason": "OOMKilled",
                                "recent_ooms": recent_ooms if window else 1,
                            },
                            priority=4,
                            confidence_score=oom_confidence,
                            observation_period=observation_period,
                            dry_run=rule.get("spec", {})
                            .get("safeguards", {})
                            .get("dryRun", False),
                        )

        except Exception as e:
            logger.error(f"Failed to evaluate pod health for {pod.metadata.name}: {e}")

        return None

    def build_label_selector(self, labels: Dict[str, str]) -> str:
        """Build Kubernetes label selector from dict"""
        if not labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in labels.items())

    async def execute_healing_action(self, action: HealingAction) -> bool:
        """Execute a healing action with proper timing and observation"""
        if action.dry_run or self.dry_run_mode:
            logger.info(
                f"DRY RUN: Would execute {action.action_type} on {action.target_resource} "
                f"(confidence: {action.confidence_score:.2f})"
            )
            HEALING_ACTIONS.labels(type=action.action_type, result="dry_run").inc()
            return True

        try:
            with HEALING_DURATION.labels(action_type=action.action_type).time():
                success = False
                
                # Record observation duration
                observation_time = datetime.now() - action.created_at
                OBSERVATION_DURATION.labels(resource_type=action.action_type).observe(
                    observation_time.total_seconds()
                )

                if action.action_type in ["scale_up", "scale_down"]:
                    success = await self.execute_scaling_action(action)
                elif action.action_type == "restart_pod":
                    success = await self.execute_pod_restart(action)
                elif action.action_type == "increase_memory":
                    success = await self.execute_memory_increase(action)
                elif action.action_type == "rollback":
                    success = await self.execute_rollback(action)

                result = "success" if success else "failure"
                HEALING_ACTIONS.labels(type=action.action_type, result=result).inc()

                # Record action in history with confidence score
                self.action_history.append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "action": action,
                        "result": result,
                        "confidence": action.confidence_score,
                        "observation_duration": observation_time.total_seconds(),
                    }
                )
                
                # Update cooldown for the target resource
                if success and action.action_type.startswith('scale'):
                    deployment_name = action.target_resource.split('/')[-1]
                    pods_pattern = f"{action.target_namespace}/{deployment_name}-"
                    for key, window in self.observer.observations.items():
                        if key.startswith(pods_pattern):
                            window.last_action_time = datetime.now()

                return success

        except Exception as e:
            logger.error(f"Failed to execute healing action {action.action_type}: {e}")
            HEALING_ACTIONS.labels(type=action.action_type, result="error").inc()
            return False

    async def execute_scaling_action(self, action: HealingAction) -> bool:
        """Execute scaling action on deployment"""
        try:
            resource_parts = action.target_resource.split("/")
            if len(resource_parts) != 2 or resource_parts[0] != "deployment":
                logger.error(f"Invalid scaling target: {action.target_resource}")
                return False

            deployment_name = resource_parts[1]
            target_replicas = action.parameters.get("replicas")

            # Scale the deployment
            body = {"spec": {"replicas": target_replicas}}
            await self.apps_v1.patch_namespaced_deployment_scale(
                name=deployment_name, namespace=action.target_namespace, body=body
            )

            logger.info(
                f"Scaled {action.target_resource} to {target_replicas} replicas"
            )
            return True

        except ApiException as e:
            logger.error(f"Failed to scale {action.target_resource}: {e}")
            return False

    async def execute_pod_restart(self, action: HealingAction) -> bool:
        """Execute pod restart by deleting it"""
        try:
            resource_parts = action.target_resource.split("/")
            if len(resource_parts) != 2 or resource_parts[0] != "pod":
                logger.error(f"Invalid restart target: {action.target_resource}")
                return False

            pod_name = resource_parts[1]

            # Delete the pod (it will be recreated by the controller)
            await self.core_v1.delete_namespaced_pod(
                name=pod_name, namespace=action.target_namespace
            )

            logger.info(f"Restarted pod {action.target_resource}")
            return True

        except ApiException as e:
            logger.error(f"Failed to restart {action.target_resource}: {e}")
            return False

    async def _find_deployment_for_pod(
        self, pod_name: str, namespace: str
    ) -> Optional[str]:
        """Find deployment name for a given pod"""
        try:
            pod = await self.core_v1.read_namespaced_pod(
                name=pod_name, namespace=namespace
            )
            owner_refs = pod.metadata.owner_references or []

            for ref in owner_refs:
                if ref.kind == "ReplicaSet":
                    rs = await self.apps_v1.read_namespaced_replica_set(
                        name=ref.name, namespace=namespace
                    )
                    for rs_ref in rs.metadata.owner_references or []:
                        if rs_ref.kind == "Deployment":
                            return rs_ref.name
            return None
        except Exception:
            return None

    def _calculate_new_memory(self, current_memory: str) -> str:
        """Calculate new memory value with 2x increase"""
        if "Mi" in current_memory:
            memory_mb = int(current_memory.replace("Mi", ""))
            return f"{memory_mb * 2}Mi"
        return "512Mi"  # Default increase

    async def execute_memory_increase(self, action: HealingAction) -> bool:
        """Execute memory increase for deployment"""
        try:
            # Find the deployment that owns this pod
            pod_name = action.target_resource.split("/")[1]
            deployment_name = await self._find_deployment_for_pod(
                pod_name, action.target_namespace
            )

            if not deployment_name:
                logger.error(f"Could not find deployment for pod {pod_name}")
                return False

            # Increase memory limits
            deployment = await self.apps_v1.read_namespaced_deployment(
                name=deployment_name, namespace=action.target_namespace
            )

            container_name = action.parameters.get("container")
            containers = deployment.spec.template.spec.containers

            for container in containers:
                if container.name == container_name:
                    if not container.resources:
                        container.resources = client.V1ResourceRequirements()
                    if not container.resources.limits:
                        container.resources.limits = {}

                    current_memory = container.resources.limits.get("memory", "256Mi")
                    new_memory = self._calculate_new_memory(current_memory)
                    container.resources.limits["memory"] = new_memory
                    break

            # Update the deployment
            await self.apps_v1.patch_namespaced_deployment(
                name=deployment_name, namespace=action.target_namespace, body=deployment
            )

            logger.info(f"Increased memory for {deployment_name}/{container_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to increase memory: {e}")
            return False

    async def execute_rollback(self, action: HealingAction) -> bool:
        """Execute deployment rollback"""
        try:
            deployment_name = action.parameters.get("deployment")
            if not deployment_name:
                logger.error("No deployment specified for rollback")
                return False

            # Trigger rollback by updating deployment annotation
            body = {
                "metadata": {
                    "annotations": {
                        "deployment.kubernetes.io/revision": str(
                            int(action.parameters.get("target_revision", "1"))
                        )
                    }
                }
            }

            await self.apps_v1.patch_namespaced_deployment(
                name=deployment_name, namespace=action.target_namespace, body=body
            )

            logger.info(f"Rolled back deployment {deployment_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to rollback deployment: {e}")
            return False

    async def rate_limit_check(self, rule: Dict) -> bool:
        """Check if we've exceeded the rate limit for actions"""
        safeguards = rule.get("spec", {}).get("safeguards", {})
        max_actions = safeguards.get("maxActionsPerHour", 10)

        now = datetime.now()
        hour_ago = now - timedelta(hours=1)

        # Count actions in the last hour
        recent_actions = [
            action
            for action in self.action_history
            if datetime.fromisoformat(action["timestamp"]) > hour_ago
        ]

        return len(recent_actions) < max_actions

    async def process_healing_rules(self):
        """Process all healing rules with observation-based decision making"""
        rules = await self.get_healing_rules()
        ACTIVE_RULES.set(len(rules))

        # Process pending actions that are ready to execute
        if self.observation_enabled:
            ready_actions = self.action_planner.get_ready_actions()
            for action in ready_actions[:5]:  # Limit concurrent ready actions
                success = await self.execute_healing_action(action)
                if not success:
                    logger.error(f"Failed to execute ready healing action: {action}")

        # Generate new healing actions
        new_actions = []

        for rule in rules:
            try:
                if not rule.get("spec", {}).get("enabled", True):
                    continue

                # Rate limiting check
                if not await self.rate_limit_check(rule):
                    logger.warning(
                        f"Rate limit exceeded for rule {rule['metadata']['name']}"
                    )
                    continue

                # Generate healing actions with observation
                scaling_actions = await self.evaluate_pod_scaling(rule)
                health_actions = await self.evaluate_pod_health(rule)

                new_actions.extend(scaling_actions)
                new_actions.extend(health_actions)

            except Exception as e:
                logger.error(
                    f"Failed to process rule {rule.get('metadata', {}).get('name', 'unknown')}: {e}"
                )

        # Sort actions by priority and confidence
        new_actions.sort(key=lambda x: (x.priority, x.confidence_score), reverse=True)

        # Add new actions to planner for observation or execute immediately if observation disabled
        for action in new_actions[:10]:  # Limit new actions per cycle
            if self.observation_enabled:
                self.action_planner.add_pending_action(action)
                logger.info(
                    f"Added action to observation queue: {action.action_type} on {action.target_resource} "
                    f"(confidence: {action.confidence_score:.2f}, observation: {action.observation_period})"
                )
            else:
                # Execute immediately if observation is disabled
                success = await self.execute_healing_action(action)
                if not success:
                    logger.error(f"Failed to execute immediate healing action: {action}")
        
        # Cleanup old observations periodically
        if datetime.now().minute % 30 == 0:  # Every 30 minutes
            self.observer.cleanup_old_observations()

    async def update_rule_status(self, rule: Dict, actions_taken: int):
        """Update the status of a healing rule"""
        try:
            name = rule["metadata"]["name"]
            namespace = rule["metadata"]["namespace"]

            status = {
                "lastHealing": datetime.now().isoformat(),
                "healingStats": {
                    "totalActions": actions_taken,
                    "lastHourActions": len(
                        [
                            a
                            for a in self.action_history
                            if datetime.fromisoformat(a["timestamp"])
                            > datetime.now() - timedelta(hours=1)
                        ]
                    ),
                },
            }

            body = {"status": status}

            await self.custom_api.patch_namespaced_custom_object_status(
                group="mlops.ai",
                version="v1",
                namespace=namespace,
                plural="infrahealingrules",
                name=name,
                body=body,
            )

        except Exception as e:
            logger.error(f"Failed to update rule status: {e}")

    async def run(self):
        """Main run loop with enhanced observation and efficiency"""
        logger.info(
            f"Starting Infrastructure Healer (observation_mode: {self.observation_enabled}, "
            f"dry_run: {self.dry_run_mode})"
        )

        # Start metrics server
        start_http_server(8080)

        while True:
            try:
                loop_start = datetime.now()
                await self.process_healing_rules()
                
                # Log performance metrics
                loop_duration = (datetime.now() - loop_start).total_seconds()
                logger.debug(f"Healing loop completed in {loop_duration:.2f}s")
                
                await asyncio.sleep(self.reconcile_interval)
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                await asyncio.sleep(10)


def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    healer = InfrastructureHealer()
    asyncio.run(healer.run())


if __name__ == "__main__":
    main()
