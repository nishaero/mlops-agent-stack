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
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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

logger = logging.getLogger(__name__)


@dataclass
class HealingAction:
    """Represents a healing action to be taken"""

    action_type: str  # scale_up, scale_down, restart, rollback
    target_resource: str
    target_namespace: str
    parameters: Dict[str, Any]
    priority: int = 1  # 1=low, 2=medium, 3=high, 4=critical
    dry_run: bool = False


class InfrastructureHealer:
    """Main Infrastructure Healing Controller"""

    def __init__(self):
        self.reconcile_interval = int(os.getenv("RECONCILE_INTERVAL", "30"))
        self.dry_run_mode = os.getenv("DRY_RUN", "false").lower() == "true"

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

        # Healing state
        self.active_rules = {}
        self.action_history = []
        self.last_actions = {}

    async def get_healing_rules(self) -> List[Dict]:
        """Get all InfraHealingRule resources"""
        try:
            rules = await self.custom_api.list_cluster_custom_object(
                group="mlops.ai", version="v1", plural="infrahealingrules"
            )
            return rules.get("items", [])
        except ApiException as e:
            if e.status != 404:
                logger.error(f"Failed to get healing rules: {e}")
            return []

    async def evaluate_pod_scaling(self, rule: Dict) -> List[HealingAction]:
        """Evaluate if pod scaling is needed based on metrics"""
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
                # Get deployments in namespace
                deployments = await self.apps_v1.list_namespaced_deployment(
                    namespace=namespace, label_selector=label_selector
                )

                for deployment in deployments.items:
                    action = await self.evaluate_deployment_scaling(
                        deployment, scaling_config, rule
                    )
                    if action:
                        actions.append(action)

            except ApiException as e:
                logger.error(f"Failed to list deployments in {namespace}: {e}")

        return actions

    async def evaluate_deployment_scaling(
        self, deployment, scaling_config: Dict, rule: Dict
    ) -> Optional[HealingAction]:
        """Evaluate scaling for a specific deployment"""
        try:
            name = deployment.metadata.name
            namespace = deployment.metadata.namespace
            current_replicas = deployment.spec.replicas or 1

            # Get pod metrics (simplified - would use metrics API in production)
            pods = await self.core_v1.list_namespaced_pod(
                namespace=namespace, label_selector=f"app={name}"
            )

            # Analyze pod health
            unhealthy_pods = 0
            total_pods = len(pods.items)

            for pod in pods.items:
                if pod.status.phase != "Running":
                    unhealthy_pods += 1
                    continue

                # Check restart count
                restart_count = sum(
                    container.restart_count or 0
                    for container in pod.status.container_statuses or []
                )

                if restart_count > 5:  # High restart count indicates issues
                    unhealthy_pods += 1

            # Determine scaling action
            unhealthy_ratio = unhealthy_pods / max(total_pods, 1)
            max_replicas = scaling_config.get("maxReplicas", 10)
            min_replicas = scaling_config.get("minReplicas", 1)

            target_replicas = current_replicas
            action_type = None

            if unhealthy_ratio > 0.5 and current_replicas < max_replicas:
                # Scale up if more than 50% pods are unhealthy
                target_replicas = min(current_replicas * 2, max_replicas)
                action_type = "scale_up"
            elif unhealthy_ratio < 0.1 and current_replicas > min_replicas:
                # Scale down if less than 10% pods are unhealthy
                target_replicas = max(current_replicas // 2, min_replicas)
                action_type = "scale_down"

            if action_type and target_replicas != current_replicas:
                return HealingAction(
                    action_type=action_type,
                    target_resource=f"deployment/{name}",
                    target_namespace=namespace,
                    parameters={
                        "replicas": target_replicas,
                        "current_replicas": current_replicas,
                        "unhealthy_ratio": unhealthy_ratio,
                    },
                    priority=3 if action_type == "scale_up" else 2,
                    dry_run=rule.get("spec", {})
                    .get("safeguards", {})
                    .get("dryRun", False),
                )

        except Exception as e:
            logger.error(
                f"Failed to evaluate deployment scaling for {deployment.metadata.name}: {e}"
            )

        return None

    async def evaluate_pod_health(self, rule: Dict) -> List[HealingAction]:
        """Evaluate pod health and generate healing actions"""
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
                    action = await self.evaluate_single_pod_health(
                        pod, health_config, rule
                    )
                    if action:
                        actions.append(action)

            except ApiException as e:
                logger.error(f"Failed to list pods in {namespace}: {e}")

        return actions

    async def evaluate_single_pod_health(
        self, pod, health_config: Dict, rule: Dict
    ) -> Optional[HealingAction]:
        """Evaluate health of a single pod"""
        try:
            name = pod.metadata.name
            namespace = pod.metadata.namespace

            # Check restart count
            restart_threshold = health_config.get("restartThreshold", 5)
            max_restart_count = 0

            for container in pod.status.container_statuses or []:
                restart_count = container.restart_count or 0
                max_restart_count = max(max_restart_count, restart_count)

            if max_restart_count > restart_threshold:
                action_type = health_config.get("crashLoopBackoffAction", "restart")

                if action_type == "restart":
                    return HealingAction(
                        action_type="restart_pod",
                        target_resource=f"pod/{name}",
                        target_namespace=namespace,
                        parameters={
                            "restart_count": max_restart_count,
                            "threshold": restart_threshold,
                        },
                        priority=3,
                        dry_run=rule.get("spec", {})
                        .get("safeguards", {})
                        .get("dryRun", False),
                    )

            # Check for OOMKilled containers
            for container in pod.status.container_statuses or []:
                if (
                    container.last_state
                    and container.last_state.terminated
                    and container.last_state.terminated.reason == "OOMKilled"
                ):

                    action_type = health_config.get(
                        "oomKilledAction", "increase-memory"
                    )

                    if action_type == "increase-memory":
                        return HealingAction(
                            action_type="increase_memory",
                            target_resource=f"pod/{name}",
                            target_namespace=namespace,
                            parameters={
                                "container": container.name,
                                "reason": "OOMKilled",
                            },
                            priority=4,
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
        """Execute a healing action"""
        if action.dry_run or self.dry_run_mode:
            logger.info(
                f"DRY RUN: Would execute {action.action_type} on {action.target_resource}"
            )
            HEALING_ACTIONS.labels(type=action.action_type, result="dry_run").inc()
            return True

        try:
            with HEALING_DURATION.labels(action_type=action.action_type).time():
                success = False

                if (
                    action.action_type == "scale_up"
                    or action.action_type == "scale_down"
                ):
                    success = await self.execute_scaling_action(action)
                elif action.action_type == "restart_pod":
                    success = await self.execute_pod_restart(action)
                elif action.action_type == "increase_memory":
                    success = await self.execute_memory_increase(action)
                elif action.action_type == "rollback":
                    success = await self.execute_rollback(action)

                result = "success" if success else "failure"
                HEALING_ACTIONS.labels(type=action.action_type, result=result).inc()

                # Record action in history
                self.action_history.append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "action": action,
                        "result": result,
                    }
                )

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
        """Process all healing rules and generate actions"""
        rules = await self.get_healing_rules()
        ACTIVE_RULES.set(len(rules))

        all_actions = []

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

                # Generate healing actions
                scaling_actions = await self.evaluate_pod_scaling(rule)
                health_actions = await self.evaluate_pod_health(rule)

                all_actions.extend(scaling_actions)
                all_actions.extend(health_actions)

            except Exception as e:
                logger.error(
                    f"Failed to process rule {rule.get('metadata', {}).get('name', 'unknown')}: {e}"
                )

        # Sort actions by priority (highest first)
        all_actions.sort(key=lambda x: x.priority, reverse=True)

        # Execute actions
        for action in all_actions[:10]:  # Limit concurrent actions
            success = await self.execute_healing_action(action)
            if not success:
                logger.error(f"Failed to execute healing action: {action}")

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
        """Main run loop"""
        logger.info("Starting Infrastructure Healer")

        # Start metrics server
        start_http_server(8080)

        while True:
            try:
                await self.process_healing_rules()
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
