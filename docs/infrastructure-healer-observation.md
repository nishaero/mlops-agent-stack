# Infrastructure Healer: Observation-Based Self-Healing

## Overview

The Infrastructure Healer has been enhanced with observation-based decision making to provide more intelligent and reliable self-healing capabilities. Instead of taking immediate action based on single-point metrics, the system now observes pod behavior and performance trends over time before making healing decisions.

## Key Features

### 🔍 **Observation-Based Decision Making**
- **Performance Tracking**: Continuous monitoring of pod metrics including restart counts, readiness, and resource usage
- **Trend Analysis**: Statistical analysis of metrics over time to identify patterns and trends
- **Confidence Scoring**: Each healing action receives a confidence score based on observation data
- **Cooldown Periods**: Prevents action flapping by enforcing cooldown periods between healing actions

### 📊 **Enhanced Metrics Collection**
```python
@dataclass
class PodMetrics:
    timestamp: datetime
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    restart_count: int = 0
    is_ready: bool = True
    phase: str = "Running"
    oom_killed: bool = False
```

### 🧠 **Intelligent Action Planning**
- **Gradual Scaling**: Conservative scaling approach (±1 replica or 50% max) instead of aggressive doubling
- **Stability Assessment**: Actions are weighted by pod stability scores
- **Pattern Recognition**: Identifies genuine issues vs. transient problems

## Architecture Components

### PodObserver
Tracks pod performance over time with rolling windows of metrics.

```python
class PodObserver:
    def __init__(self):
        self.observations: Dict[str, ObservationWindow] = {}
        self.min_observation_period = timedelta(minutes=2)
```

**Key Methods:**
- `observe_pod()`: Collects current metrics for a pod
- `get_trend()`: Calculates performance trends using linear regression
- `cleanup_old_observations()`: Manages memory by removing old data

### ObservationWindow
Maintains rolling window of metrics with trend analysis capabilities.

```python
def get_trend(self, metric_name: str, window_minutes: int = 10) -> Tuple[float, float]:
    """Returns (slope, confidence) for the specified metric trend"""
```

**Features:**
- Linear regression-based trend calculation
- Confidence scoring based on data volume and consistency
- Stability assessment across multiple metrics
- Cooldown period management

### ActionPlanner
Evaluates observations and determines when actions should be taken.

```python
class ActionPlanner:
    def calculate_scaling_confidence(self, deployment_name: str, namespace: str, 
                                   current_replicas: int, target_replicas: int) -> float:
        """Returns confidence score (0.0-1.0) for scaling action"""
```

**Intelligence Features:**
- **Scaling Confidence**: Considers stability, trends, and change magnitude
- **Restart Confidence**: Analyzes restart patterns vs. one-off events
- **Pending Action Queue**: Manages actions waiting for observation period completion

## Configuration

### Environment Variables
```bash
# Enable/disable observation mode (default: true)
OBSERVATION_MODE=true

# Reconcile interval in seconds (default: 30)
RECONCILE_INTERVAL=30

# Enable dry-run mode (default: false)
DRY_RUN=false
```

### Healing Rule Configuration
```yaml
apiVersion: mlops.ai/v1
kind: InfraHealingRule
metadata:
  name: observed-scaling-rule
spec:
  enabled: true
  scope:
    namespaces: ["production"]
    labels:
      app: "web-service"
  scaling:
    pods:
      enabled: true
      minReplicas: 2
      maxReplicas: 10
      scaleUpThreshold: "75%"    # Scale up when 75% pods unhealthy
      scaleDownThreshold: "25%"  # Scale down when <25% pods unhealthy
  healthChecks:
    pods:
      restartThreshold: 5
      crashLoopBackoffAction: "restart"
      oomKilledAction: "increase-memory"
  safeguards:
    dryRun: false
    maxActionsPerHour: 10
```

## Observation Periods

Different action types have different observation periods to balance responsiveness with stability:

| Action Type | Default Observation Period | Reasoning |
|-------------|----------------------------|-----------|
| Scale Up | 2 minutes | Urgent - address capacity issues quickly |
| Scale Down | 5 minutes | Conservative - ensure stability before reducing capacity |
| Pod Restart | 3 minutes | Moderate - confirm restart pattern exists |
| Memory Increase | 2 minutes | Urgent - address OOM conditions quickly |
| Rollback | 5 minutes | Conservative - major change requiring confidence |

## Confidence Thresholds

Actions are only executed when confidence scores meet minimum thresholds:

| Action Type | Minimum Confidence | Factors Considered |
|-------------|-------------------|-------------------|
| Scale Up | 0.6 | Pod stability, restart trends, unhealthy ratio |
| Scale Down | 0.7 | Higher threshold for capacity reduction |
| Pod Restart | 0.5 | Restart count trends, stability history |
| Memory Increase | 0.6 | OOM frequency, resource usage patterns |
| Rollback | 0.8 | Highest threshold for major changes |

## Decision Logic Improvements

### Scaling Decisions
```python
# Before: Aggressive scaling
if unhealthy_ratio > 0.5:
    target_replicas = current_replicas * 2  # Double replicas

# After: Gradual scaling with observation
if unhealthy_ratio > scale_up_threshold and current_replicas < max_replicas:
    if avg_stability < 0.6:  # Low stability = more conservative
        target_replicas = current_replicas + 1
    else:
        target_replicas = min(current_replicas + max(1, current_replicas // 2), max_replicas)
```

### Restart Decisions
```python
# Before: Immediate restart on threshold
if restart_count > threshold:
    restart_pod()

# After: Pattern-based restart with confidence
if restart_count > threshold:
    restart_trend, confidence = window.get_trend('restart_count')
    if restart_trend > 0 and confidence > 0.5:  # Increasing trend
        schedule_restart_with_observation()
```

## Metrics and Monitoring

### New Prometheus Metrics
```python
# Observation duration tracking
OBSERVATION_DURATION = Histogram(
    "mlops_observation_duration_seconds", 
    "Time spent observing before action", 
    ["resource_type"]
)

# Confidence scoring
CONFIDENCE_SCORE = Gauge(
    "mlops_action_confidence", 
    "Confidence score for healing actions", 
    ["action_type"]
)
```

### Enhanced Action History
```python
{
    "timestamp": "2024-01-15T10:30:00Z",
    "action": HealingAction(...),
    "result": "success",
    "confidence": 0.85,
    "observation_duration": 180.5
}
```

## Benefits

### 🎯 **Reduced False Positives**
- Observation periods filter out transient issues
- Trend analysis identifies genuine problems vs. noise
- Confidence scoring prevents low-certainty actions

### 🛡️ **Improved Stability**
- Gradual scaling prevents resource churn
- Cooldown periods prevent action flapping
- Conservative thresholds for destructive actions

### 📈 **Better Resource Utilization**
- Pattern recognition optimizes scaling decisions
- Memory increase only for persistent OOM patterns
- Intelligent rollback triggers

### 🔍 **Enhanced Observability**
- Detailed metrics on observation and confidence
- Action history with reasoning
- Performance trend visualization

## Migration Guide

### Existing Deployments
The observation-based healer is backward compatible with existing `InfraHealingRule` resources. To benefit from enhanced features:

1. **Enable Observation Mode** (default enabled):
   ```bash
   kubectl set env deployment/infrastructure-healer OBSERVATION_MODE=true
   ```

2. **Adjust Safeguards** for more conservative healing:
   ```yaml
   spec:
     safeguards:
       maxActionsPerHour: 5  # Reduced from default 10
       dryRun: true          # Test observation logic first
   ```

3. **Monitor Confidence Metrics** to tune thresholds:
   ```promql
   mlops_action_confidence{action_type="scale_up"}
   ```

### Gradual Rollout
1. **Phase 1**: Deploy with `DRY_RUN=true` to observe without actions
2. **Phase 2**: Enable actions with conservative thresholds
3. **Phase 3**: Tune confidence thresholds based on metrics

## Example Scenarios

### Scenario 1: Pod Restart Storm
**Before**: Immediate restart after 5 restarts → potential restart loop
**After**: Observe restart trend over 3 minutes → only restart if trend is increasing

### Scenario 2: Traffic Spike Scaling
**Before**: Double replicas immediately on 50% unhealthy pods
**After**: Scale up by 1-2 replicas based on stability, observe for 2 minutes

### Scenario 3: Memory Pressure
**Before**: Increase memory on first OOM event
**After**: Observe OOM frequency over 2 minutes → increase only for persistent pattern

This observation-based approach transforms the Infrastructure Healer from a reactive system into an intelligent, pattern-aware self-healing platform that makes informed decisions based on comprehensive analysis of pod behavior and performance trends.