# MLOps Agent Stack - Production Operations Guide

## 🚀 Quick Start

### Prerequisites
- Kubernetes cluster v1.24+
- Helm v3.12+
- kubectl configured for your cluster
- Adequate resources (see [Resource Requirements](#resource-requirements))

### Installation

```bash
# Clone the repository
git clone https://github.com/nishaero/mlops-agent-stack.git
cd mlops-agent-stack

# Deploy with default configuration
./scripts/deployment/deploy.sh

# Deploy with GitHub integration
GITHUB_TOKEN="your_token" ./scripts/deployment/deploy.sh

# Production deployment
./scripts/deployment/deploy.sh --namespace production --image-tag v1.0.0
```

### Verification

```bash
# Check pod status
kubectl get pods -n mlops-agent-stack

# Run integration tests
helm test mlops-agent-stack -n mlops-agent-stack

# Check service health
kubectl port-forward svc/mlops-agent-stack-ai-engine 8080:8080
curl http://localhost:8080/health
```

## 📊 Monitoring & Observability

### Dashboards

Access Grafana dashboards:
- **AI Metrics**: Real-time model performance and GPU utilization
- **Infrastructure Health**: Pod status, healing actions, and resource usage
- **Code Quality**: Fix success rates and repository health

```bash
# Access Grafana
kubectl port-forward svc/mlops-agent-stack-grafana 3000:3000
# Open http://localhost:3000 (admin/password from secret)
```

### Key Metrics to Monitor

| Metric | Threshold | Action |
|--------|-----------|--------|
| AI Engine Availability | < 99.5% | Check pod health, review logs |
| Model Latency P95 | > 2s | Scale up, check GPU utilization |
| Healing Actions Rate | > 1/min | Investigate infrastructure issues |
| Fix Success Rate | < 70% | Review code patterns, model tuning |
| GPU Utilization | > 90% | Scale horizontally or upgrade |

### Alerting

Critical alerts are sent to:
- Slack: `#mlops-critical` 
- Email: `oncall@company.com`
- PagerDuty: Auto-escalation after 15 minutes

## 🔧 Configuration Management

### Environment-Specific Configurations

```bash
# Development
helm upgrade mlops-agent-stack charts/ \
  --values charts/values.yaml \
  --values environments/dev-values.yaml

# Staging
helm upgrade mlops-agent-stack charts/ \
  --values charts/values.yaml \
  --values environments/staging-values.yaml

# Production
helm upgrade mlops-agent-stack charts/ \
  --values charts/values.yaml \
  --values environments/prod-values.yaml
```

### Security Configuration

```yaml
# Enable strict security policies
security:
  podSecurityStandards:
    enabled: true
    enforce: "restricted"
  gatekeeper:
    enabled: true
    requireDigests: true
  networkPolicies:
    enabled: true
```

## 🛠 Operational Procedures

### Scaling Operations

#### Manual Scaling
```bash
# Scale AI Engine
kubectl scale deployment mlops-agent-stack-ai-engine --replicas=5

# Scale with HPA
kubectl patch hpa mlops-agent-stack-ai-engine --patch '{"spec":{"maxReplicas":20}}'
```

#### Auto-scaling Configuration
```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

### Backup & Recovery

#### Daily Backup Verification
```bash
# Check backup job status
kubectl get cronjobs -n mlops-agent-stack

# View backup logs
kubectl logs -l component=backup -n mlops-agent-stack

# Test backup integrity
kubectl exec deployment/mlops-agent-stack-ai-engine -- ls -la /backup
```

#### Disaster Recovery Procedure
1. **Assessment**: Determine scope of failure
2. **Isolation**: Isolate affected components
3. **Recovery**: Restore from latest backup
4. **Validation**: Run integration tests
5. **Monitoring**: Enhanced monitoring for 24h

### Model Management

#### Model Updates
```bash
# Update AI models
kubectl create configmap new-model-config --from-file=model.pkl
kubectl patch deployment mlops-agent-stack-ai-engine \
  --patch '{"spec":{"template":{"metadata":{"annotations":{"deployment.kubernetes.io/revision":"'$(date +%s)'"}}}}'
```

#### Model Performance Monitoring
```bash
# Check model accuracy
kubectl exec deployment/mlops-agent-stack-ai-engine -- \
  curl localhost:8080/metrics | grep model_accuracy

# View model inference metrics
kubectl exec deployment/mlops-agent-stack-ai-engine -- \
  curl localhost:8080/api/v1/models/stats
```

## 📈 Performance Optimization

### Resource Optimization

#### CPU and Memory Tuning
```yaml
resources:
  requests:
    cpu: "1000m"     # Start conservative
    memory: "2Gi"
  limits:
    cpu: "2000m"     # Allow burst capacity
    memory: "4Gi"
```

#### GPU Optimization
```yaml
resources:
  limits:
    nvidia.com/gpu: 1
  requests:
    nvidia.com/gpu: 1
```

### Network Optimization

#### Service Mesh (Optional)
```yaml
networking:
  istio:
    enabled: true
    mtls: true
    telemetry: true
```

## 🔒 Security Hardening

### Pod Security Standards
```yaml
security:
  podSecurityStandards:
    enabled: true
    enforce: "restricted"
  containerSecurityContext:
    runAsNonRoot: true
    readOnlyRootFilesystem: true
    allowPrivilegeEscalation: false
    capabilities:
      drop: ["ALL"]
```

### Network Security
```yaml
security:
  networkPolicies:
    enabled: true
    defaultDeny: true
    allowMonitoring: true
```

### Image Security
```yaml
security:
  imageScanning:
    enabled: true
    failOnHigh: true
    failOnCritical: true
  gatekeeper:
    requireDigests: true
    allowedRegistries:
      - "ghcr.io"
      - "gcr.io"
```

## 🚨 Troubleshooting

### Common Issues

#### AI Engine Not Starting
```bash
# Check pod logs
kubectl logs deployment/mlops-agent-stack-ai-engine

# Check resource constraints
kubectl describe pod -l component=ai-engine

# Verify GPU availability
kubectl get nodes -o yaml | grep nvidia.com/gpu
```

#### High Memory Usage
```bash
# Check memory usage by pod
kubectl top pods -n mlops-agent-stack

# Scale up if needed
kubectl patch hpa mlops-agent-stack-ai-engine \
  --patch '{"spec":{"targetMemoryUtilizationPercentage":70}}'
```

#### Healing Actions Not Working
```bash
# Check infrastructure healer logs
kubectl logs deployment/mlops-agent-stack-infrastructure-healer

# Verify RBAC permissions
kubectl auth can-i "*" "*" --as=system:serviceaccount:mlops-agent-stack:mlops-agent-stack-infrastructure-healer
```

### Log Analysis

```bash
# View aggregated logs with Loki
kubectl port-forward svc/mlops-agent-stack-loki 3100:3100

# Query error logs
curl -G "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={namespace="mlops-agent-stack"} |= "ERROR"'
```

## 📞 Support & Escalation

### Support Tiers

1. **L1 Support**: Basic monitoring, restarts, scaling
2. **L2 Support**: Configuration changes, debugging
3. **L3 Support**: Code changes, architectural decisions

### Escalation Matrix

| Severity | Initial Response | Resolution Target | Escalation |
|----------|------------------|-------------------|------------|
| P0 - Critical | 15 minutes | 4 hours | Immediate |
| P1 - High | 1 hour | 8 hours | After 2 hours |
| P2 - Medium | 4 hours | 24 hours | After 8 hours |
| P3 - Low | 24 hours | 72 hours | After 48 hours |

### Contact Information

- **On-call Engineer**: `oncall@company.com`
- **Slack Channel**: `#mlops-support`
- **Documentation**: [Internal Wiki](https://wiki.company.com/mlops)
- **Runbooks**: [Runbook Repository](https://github.com/company/mlops-runbooks)

## 📚 Additional Resources

- [Architecture Documentation](../architecture/README.md)
- [API Documentation](../api/README.md)
- [Monitoring Runbooks](../runbooks/monitoring.md)
- [Security Guidelines](../security/guidelines.md)
- [Performance Benchmarks](../benchmarks/README.md)