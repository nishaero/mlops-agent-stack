# Quick Start Guide

This guide will help you get the MLOps Agent Stack up and running in your Kubernetes cluster.

## Prerequisites

- Kubernetes cluster (v1.24+)
- Helm 3.12+
- kubectl configured to access your cluster
- At least 8GB RAM and 4 CPU cores available in the cluster
- Storage class for persistent volumes

## Step 1: Clone the Repository

```bash
git clone https://github.com/nishaero/mlops-agent-stack.git
cd mlops-agent-stack
```

## Step 2: Configure Your Environment

### Required Secrets

Create a `.env` file with your configuration:

```bash
# GitHub Integration (optional but recommended)
export GITHUB_TOKEN="ghp_your_github_personal_access_token"

# GitLab Integration (optional)
export GITLAB_TOKEN="glpat-your_gitlab_token"

# Grafana Admin Password (optional - will be auto-generated if not provided)
export GRAFANA_ADMIN_PASSWORD="your_secure_password"
```

Load the environment:
```bash
source .env
```

### Customize Values (Optional)

Edit `charts/values.yaml` to customize your deployment:

```yaml
# Enable/disable components
aiEngine:
  enabled: true
  replicaCount: 2

infrastructureHealer:
  enabled: true
  config:
    dryRun: false  # Set to true for testing

codeAutofix:
  enabled: true
  github:
    enabled: true  # Requires GITHUB_TOKEN

# Resource allocation
resources:
  limits:
    cpu: 2000m
    memory: 4Gi
  requests:
    cpu: 1000m
    memory: 2Gi
```

## Step 3: Deploy the Stack

### Simple Deployment

```bash
./scripts/deployment/deploy.sh
```

### Advanced Deployment Options

```bash
# Deploy to a specific namespace
./scripts/deployment/deploy.sh --namespace production

# Dry run to test configuration
./scripts/deployment/deploy.sh --dry-run

# Use custom values file
./scripts/deployment/deploy.sh --values-file ./my-values.yaml

# Deploy specific image version
./scripts/deployment/deploy.sh --image-tag v1.2.3 --image-registry ghcr.io/myorg/
```

## Step 4: Verify Installation

```bash
# Check all pods are running
kubectl get pods -n mlops-agent-stack

# Check services
kubectl get services -n mlops-agent-stack

# Check custom resources
kubectl get autofixpolicies,infrahealingrules,cloudconfigs --all-namespaces
```

## Step 5: Access the UI

### Grafana Dashboard

```bash
# Get Grafana URL (if using LoadBalancer)
kubectl get svc grafana -n mlops-agent-stack

# Or port-forward for local access
kubectl port-forward svc/grafana 3000:80 -n mlops-agent-stack
```

Access at: http://localhost:3000
- Username: `admin`
- Password: Check the secret or use the one you set

### Prometheus

```bash
kubectl port-forward svc/prometheus-server 9090:80 -n mlops-agent-stack
```

Access at: http://localhost:9090

## Step 6: Configure Policies

### Create an AutoFix Policy

```yaml
apiVersion: mlops.ai/v1
kind: AutoFixPolicy
metadata:
  name: my-app-autofix
  namespace: default
spec:
  enabled: true
  repositories:
  - url: "https://github.com/myorg/my-app"
    branch: "main"
    allowedPaths:
    - "src/"
    - "lib/"
    excludedPaths:
    - "src/secrets/"
  autoMerge:
    enabled: false
    maxRiskLevel: "low"
  riskAssessment:
    dryRunFirst: true
    maxChangesPerPR: 5
```

Apply the policy:
```bash
kubectl apply -f my-autofix-policy.yaml
```

### Create an Infrastructure Healing Rule

```yaml
apiVersion: mlops.ai/v1
kind: InfraHealingRule
metadata:
  name: my-app-healing
  namespace: default
spec:
  enabled: true
  scope:
    namespaces: ["default"]
    labels:
      app: "my-application"
  scaling:
    pods:
      enabled: true
      maxReplicas: 10
      scaleUpThreshold: "75%"
  healthChecks:
    pods:
      restartThreshold: 3
      crashLoopBackoffAction: "restart"
  safeguards:
    dryRun: false
    maxActionsPerHour: 5
```

Apply the rule:
```bash
kubectl apply -f my-healing-rule.yaml
```

## Step 7: Monitor the System

### View Logs

```bash
# AI Engine logs
kubectl logs -f deployment/mlops-agent-stack-ai-engine -n mlops-agent-stack

# Infrastructure Healer logs
kubectl logs -f deployment/mlops-agent-stack-infrastructure-healer -n mlops-agent-stack

# Code Autofix logs
kubectl logs -f deployment/mlops-agent-stack-code-autofix -n mlops-agent-stack
```

### Check Metrics

Visit the Grafana dashboards:
- AI Metrics Dashboard
- Infrastructure Health Dashboard
- Code Quality Dashboard

### View Alerts

Check AlertManager for any active alerts:
```bash
kubectl port-forward svc/alertmanager 9093:9093 -n mlops-agent-stack
```

## Troubleshooting

### Common Issues

1. **Pods stuck in Pending state**
   ```bash
   kubectl describe pod <pod-name> -n mlops-agent-stack
   ```
   Usually indicates resource constraints or storage issues.

2. **CRDs not found**
   ```bash
   kubectl get crd | grep mlops.ai
   ```
   Ensure CRDs are installed properly.

3. **GitHub integration not working**
   - Verify the GitHub token has the required permissions
   - Check the secret exists: `kubectl get secret github-token -n mlops-agent-stack`

4. **High memory usage**
   - Adjust resource limits in values.yaml
   - Consider enabling model quantization for AI components

### Getting Help

1. Check the logs of the problematic component
2. Review the [Architecture Documentation](docs/architecture/README.md)
3. Open an issue on GitHub with:
   - Your Kubernetes version
   - Deployment configuration
   - Error logs
   - Steps to reproduce

## Next Steps

1. **Configure Monitoring**: Set up additional Prometheus exporters for your applications
2. **Customize AI Models**: Train models on your specific data patterns
3. **Setup GitOps**: Configure Flux or ArgoCD for automated deployments
4. **Security Hardening**: Review and customize RBAC policies
5. **Scaling**: Configure HPA and cluster autoscaling for production workloads

## Uninstalling

To completely remove the MLOps Agent Stack:

```bash
# Remove the Helm release
helm uninstall mlops-agent-stack -n mlops-agent-stack

# Delete the namespace
kubectl delete namespace mlops-agent-stack

# Remove CRDs (optional - will remove all custom resources)
kubectl delete crd autofixpolicies.mlops.ai
kubectl delete crd infrahealingrules.mlops.ai
kubectl delete crd cloudconfigs.mlops.ai
```

## Production Considerations

### Security
- Use image scanning in your CI/CD pipeline
- Enable Pod Security Standards
- Configure network policies
- Regular security audits

### Monitoring
- Set up log aggregation
- Configure comprehensive alerting
- Monitor resource usage and costs
- Implement SLO/SLI tracking

### Backup and Recovery
- Regular etcd backups
- Persistent volume backups
- Disaster recovery testing
- Multi-region deployment for critical workloads

For detailed configuration options, see the [Configuration Guide](docs/configuration.md).
For production deployment best practices, see the [Production Guide](docs/production.md).