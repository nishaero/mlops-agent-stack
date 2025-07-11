# MLOps AI Agent Stack

A production-grade, cloud-agnostic AI agent cluster for Kubernetes that autonomously monitors infrastructure, analyzes logs/metrics with AI models, self-heals infrastructure issues, and fixes application bugs through automated GitOps workflows.

![MLOps Agent Stack](https://img.shields.io/badge/Status-Production%20Ready-green)
![Kubernetes](https://img.shields.io/badge/Kubernetes-1.24%2B-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 🚀 What is MLOps Agent Stack?

The MLOps Agent Stack is an intelligent, autonomous system that:

- **🔍 Monitors** your Kubernetes infrastructure in real-time
- **🧠 Analyzes** logs and metrics using advanced AI models 
- **🔧 Self-heals** infrastructure issues automatically
- **💻 Fixes** application bugs by generating and submitting code patches
- **🔐 Maintains** security and compliance through policy enforcement
- **📊 Provides** comprehensive observability and insights

## ✨ Key Features

### 🤖 AI-Powered Analysis
- **LSTM-based anomaly detection** for time-series metrics
- **BERT-powered log analysis** for error classification and root cause analysis
- **Graph neural networks** for dependency mapping and impact assessment
- **Real-time processing** with confidence scoring and severity assessment

### 🏥 Self-Healing Infrastructure
- **Automated pod scaling** based on resource utilization and health metrics
- **Node replacement** for unhealthy infrastructure components
- **Intelligent rollbacks** for failed deployments
- **Multi-cloud support** through Cluster API abstraction

### 🛠️ Code-Level Autofixing
- **Error-to-code mapping** from stack traces and logs
- **LLM-powered patch generation** using fine-tuned CodeLlama models
- **Automated PR creation** with comprehensive testing and risk assessment
- **GitOps integration** with GitHub/GitLab workflows

### 🔒 Enterprise Security
- **Policy-as-Code** with Open Policy Agent integration
- **RBAC controls** with least-privilege access
- **Code signing** and artifact verification with Cosign
- **Audit trails** and compliance reporting

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Data Collection │    │  AI Analysis    │    │ Action Engine   │
│                 │    │                 │    │                 │
│ • Prometheus    │───▶│ • Anomaly Det.  │───▶│ • Infra Healer  │
│ • FluentBit     │    │ • Log Analysis  │    │ • Code Autofix  │
│ • OpenTelemetry │    │ • Root Cause    │    │ • GitOps        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Policy Engine   │
                       │                 │
                       │ • OPA Policies  │
                       │ • RBAC Control  │
                       │ • Risk Assess.  │
                       └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

#### Infrastructure Requirements
- **Kubernetes cluster** (v1.24+)
  - Minimum 3 nodes (for high availability)
  - 8GB+ RAM per node, 4+ CPU cores per node
  - 100GB+ available storage with a default StorageClass
  - LoadBalancer support (cloud provider or MetalLB)
  - CNI plugin with Network Policy support (e.g., Calico, Cilium)

#### Command Line Tools
- **kubectl** configured to access your cluster
- **Helm** 3.12+ for package management
- **Docker** or equivalent container runtime (for building custom images)
- **Git** for repository operations

#### Development Dependencies (if building from source)
- **Python** 3.11+ with pip
- **Node.js** 18+ and npm (for web dashboard components)
- **Go** 1.19+ (for custom operators)

#### Cloud & External Services
- **Container Registry** access (Docker Hub, GitHub Container Registry, or cloud provider registry)
- **GitHub/GitLab** account with API tokens (for automated PR creation)
- **Prometheus/Grafana** compatible monitoring (or use included stack)

#### Optional but Recommended
- **Ingress Controller** (nginx, traefik) for external access
- **Cert-Manager** for automatic TLS certificate management
- **Backup solution** (Velero) for cluster backups
- **Service Mesh** (Istio, Linkerd) for advanced traffic management

### Environment Configuration

Before installation, configure the required environment variables:

```bash
# Required: GitHub integration for automated PR creation
export GITHUB_TOKEN="ghp_your_github_personal_access_token"

# Required: Admin password for Grafana dashboard
export GRAFANA_ADMIN_PASSWORD="secure_admin_password"

# Optional: Custom container registry (defaults to ghcr.io)
export CONTAINER_REGISTRY="your-registry.com"

# Optional: Slack/Teams webhooks for notifications
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export TEAMS_WEBHOOK_URL="https://outlook.office.com/webhook/..."

# Optional: Custom namespace (defaults to mlops-agent-stack)
export MLOPS_NAMESPACE="mlops-production"

# Optional: Environment type for configuration selection
export ENVIRONMENT="production"  # Options: development, staging, production

# Optional: Enable debug logging
export DEBUG_MODE="false"

# Optional: Custom storage class
export STORAGE_CLASS="fast-ssd"
```

### Installation

```bash
# Clone the repository
git clone https://github.com/nishaero/mlops-agent-stack.git
cd mlops-agent-stack

# Set up environment (optional but recommended)
export GITHUB_TOKEN="your_github_token"
export GRAFANA_ADMIN_PASSWORD="secure_password"

# Deploy the stack
./scripts/deployment/deploy.sh
```

### Verify Installation

```bash
# Check pods are running
kubectl get pods -n mlops-agent-stack

# Access Grafana dashboard
kubectl port-forward svc/grafana 3000:80 -n mlops-agent-stack
```

Visit http://localhost:3000 (admin/your_password)

## 🧪 Setup & Testing Guide

### Pre-Deployment Checks

Before deploying, verify your cluster meets the requirements:

```bash
# Check Kubernetes version (should be 1.24+)
kubectl version --short

# Check available resources (need 8GB+ RAM, 4+ CPU)
kubectl top nodes

# Check if you have a default storage class
kubectl get storageclass

# Verify Helm is installed (should be 3.12+)
helm version --short
```

### Detailed Setup Instructions

1. **Prepare Your Environment**
   ```bash
   # Clone and navigate to repository
   git clone https://github.com/nishaero/mlops-agent-stack.git
   cd mlops-agent-stack
   
   # Create environment configuration
   cat > .env << EOF
   export GITHUB_TOKEN="your_github_token_here"
   export GRAFANA_ADMIN_PASSWORD="secure_password_123"
   export NAMESPACE="mlops-agent-stack"
   EOF
   
   # Load configuration
   source .env
   ```

2. **Deploy the Stack**
   ```bash
   # Deploy with verification
   ./scripts/deployment/deploy.sh --namespace $NAMESPACE
   
   # Or deploy with dry-run to check configuration first
   ./scripts/deployment/deploy.sh --dry-run
   ```

3. **Verify Basic Deployment**
   ```bash
   # Check all pods are running (should show 6-8 pods)
   kubectl get pods -n $NAMESPACE
   
   # Expected output:
   # NAME                                        READY   STATUS    RESTARTS   AGE
   # mlops-agent-stack-ai-engine-xxx             1/1     Running   0          2m
   # mlops-agent-stack-code-autofix-xxx          1/1     Running   0          2m
   # mlops-agent-stack-infrastructure-healer-xxx 1/1     Running   0          2m
   # grafana-xxx                                 1/1     Running   0          2m
   # prometheus-server-xxx                       1/1     Running   0          2m
   ```

### Simple Health Check Tests

#### Test 1: Component Health Endpoints
```bash
# Check AI Engine health
kubectl port-forward svc/mlops-agent-stack-ai-engine 8080:8080 -n $NAMESPACE &
curl -f http://localhost:8080/health
# Expected: {"status": "healthy", "timestamp": "..."}

# Check Infrastructure Healer health  
kubectl port-forward svc/mlops-agent-stack-infrastructure-healer 8081:8080 -n $NAMESPACE &
curl -f http://localhost:8081/health

# Check Code Autofix health
kubectl port-forward svc/mlops-agent-stack-code-autofix 8082:8080 -n $NAMESPACE &
curl -f http://localhost:8082/health

# Stop port-forwards
pkill -f "kubectl port-forward"
```

#### Test 2: Custom Resource Definitions
```bash
# Verify CRDs are installed
kubectl get crd | grep mlops.ai
# Expected output:
# autofixpolicies.mlops.ai
# cloudconfigs.mlops.ai  
# infrahealingrules.mlops.ai

# Create a test policy to verify CRD functionality
kubectl apply -f - << EOF
apiVersion: mlops.ai/v1
kind: AutoFixPolicy
metadata:
  name: test-policy
  namespace: $NAMESPACE
spec:
  enabled: false
  repositories: []
  autoMerge:
    enabled: false
EOF

# Verify policy was created
kubectl get autofixpolicies -n $NAMESPACE test-policy
```

#### Test 3: Metrics Collection
```bash
# Check Prometheus is collecting metrics
kubectl port-forward svc/prometheus-server 9090:80 -n $NAMESPACE &
sleep 5

# Query for MLOps metrics
curl -s "http://localhost:9090/api/v1/query?query=mlops_anomalies_detected_total" | grep -o '"status":"success"'
# Expected: "status":"success"

pkill -f "kubectl port-forward"
```

#### Test 4: Log Collection
```bash
# Check if logs are being collected
kubectl logs -l app.kubernetes.io/name=mlops-agent-stack -n $NAMESPACE --tail=10

# Check for specific startup messages
kubectl logs -l component=ai-engine -n $NAMESPACE | grep -i "starting\|ready\|initialized"
```

### Automated Test Suite

#### Quick Test Script (Recommended)
```bash
# Run the comprehensive test suite
./scripts/test-deployment.sh

# Run with custom namespace
./scripts/test-deployment.sh --namespace my-mlops-stack

# With extended timeout
./scripts/test-deployment.sh --timeout 600
```

This script runs all tests automatically and provides a comprehensive report.

#### Operator-Specific Validation
```bash
# Install aiohttp for the validation script
pip install aiohttp

# Validate all operators (requires port-forwarding)
python scripts/validate-operators.py

# With custom namespace and timeout
python scripts/validate-operators.py --namespace my-mlops-stack --timeout 60

# Save detailed results to file
python scripts/validate-operators.py --output validation-results.json --verbose
```

#### Manual Integration Tests
```bash
# Install test dependencies
pip install -r operators/ai-engine/requirements.txt pytest

# Run unit tests for all operators
python -m pytest operators/ -v
# Expected: All tests should pass

# Run integration tests using Helm
helm test mlops-agent-stack -n $NAMESPACE
# Expected: test-integration-xxx pod should complete successfully
```

#### Performance Verification Tests
```bash
# Test 5: AI Engine Processing
# Create sample metrics data
kubectl apply -f - << EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-metrics
  namespace: $NAMESPACE
data:
  metrics.json: |
    {
      "timestamp": "$(date -Iseconds)",
      "cpu_usage": 75.5,
      "memory_usage": 60.2,
      "pod_restarts": 0
    }
EOF

# Check if AI engine processes the data (check logs)
kubectl logs -l component=ai-engine -n $NAMESPACE --tail=20 | grep -i "processing\|analyzing"
```

#### Test 6: Infrastructure Healing Simulation
```bash
# Create a test deployment to trigger healing
kubectl create deployment test-app --image=nginx --replicas=1 -n $NAMESPACE
kubectl label deployment test-app mlops.ai/healing=enabled -n $NAMESPACE

# Scale to trigger monitoring
kubectl scale deployment test-app --replicas=5 -n $NAMESPACE

# Check healing logs (should show observation period)
kubectl logs -l component=infrastructure-healer -n $NAMESPACE --tail=20 | grep -i "observing\|scaling\|healing"

# Cleanup test deployment
kubectl delete deployment test-app -n $NAMESPACE
```

### Monitoring Dashboard Verification

#### Access Grafana Dashboard
```bash
# Get Grafana admin password (if not set during deployment)
kubectl get secret grafana-admin-secret -n $NAMESPACE -o jsonpath='{.data.password}' | base64 -d
echo

# Access Grafana
kubectl port-forward svc/grafana 3000:80 -n $NAMESPACE
# Visit http://localhost:3000
# Login: admin / <your_password>

# Expected dashboards:
# - MLOps AI Metrics
# - Infrastructure Health  
# - Code Quality Metrics
# - Security Dashboard
```

### Troubleshooting Common Issues

#### Issue 1: Pods Not Starting
```bash
# Check events
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp'

# Check pod logs
kubectl describe pod -l app.kubernetes.io/name=mlops-agent-stack -n $NAMESPACE

# Check resource limits
kubectl top pods -n $NAMESPACE
```

#### Issue 2: Health Checks Failing
```bash
# Check service endpoints
kubectl get endpoints -n $NAMESPACE

# Verify network policies
kubectl get networkpolicies -n $NAMESPACE

# Test internal connectivity
kubectl run debug --image=nicolaka/netshoot -it --rm --restart=Never -n $NAMESPACE -- /bin/bash
# Then inside the pod: nslookup mlops-agent-stack-ai-engine
```

#### Issue 3: Metrics Not Collecting
```bash
# Check Prometheus targets
kubectl port-forward svc/prometheus-server 9090:80 -n $NAMESPACE &
# Visit http://localhost:9090/targets
# All targets should be "UP"

# Check ServiceMonitor resources
kubectl get servicemonitor -n $NAMESPACE
```

#### Issue 4: Test Scripts Failing
```bash
# For test-deployment.sh issues:
# Check prerequisites
kubectl cluster-info
helm version

# For validate-operators.py issues:
# Install missing dependencies
pip install aiohttp

# Check port-forwarding
kubectl port-forward svc/mlops-agent-stack-ai-engine 8080:8080 -n $NAMESPACE &
curl http://localhost:8080/health

# Kill orphaned port-forwards
pkill -f "kubectl port-forward"
```

#### Issue 5: Permission Errors
```bash
# Check RBAC permissions
kubectl auth can-i get pods --namespace=$NAMESPACE
kubectl auth can-i create configmaps --namespace=$NAMESPACE

# Check service account
kubectl get serviceaccount -n $NAMESPACE
kubectl describe serviceaccount default -n $NAMESPACE
```

### Clean Test Environment
```bash
# Remove test resources
kubectl delete configmap test-metrics -n $NAMESPACE --ignore-not-found
kubectl delete autofixpolicy test-policy -n $NAMESPACE --ignore-not-found

# For complete cleanup
helm uninstall mlops-agent-stack -n $NAMESPACE
kubectl delete namespace $NAMESPACE
kubectl delete crd autofixpolicies.mlops.ai infrahealingrules.mlops.ai cloudconfigs.mlops.ai
```

### Quick Reference: Testing Commands

| Test Type | Command | Expected Result |
|-----------|---------|-----------------|
| **🚀 Full Test Suite** | `./scripts/test-deployment.sh` | All tests pass ✅ |
| **🔧 Operator Validation** | `python scripts/validate-operators.py` | All operators healthy ✅ |
| **📊 Pod Health** | `kubectl get pods -n mlops-agent-stack` | All pods Running/Ready |
| **💗 Component Health** | `curl http://localhost:8080/health` | `{"status": "healthy"}` |
| **📈 Metrics** | `curl http://localhost:9090/metrics` | Prometheus metrics |
| **📋 Logs** | `kubectl logs -f -l app.kubernetes.io/name=mlops-agent-stack -n mlops-agent-stack` | Live log output |
| **⚙️ CRDs** | `kubectl get crd \| grep mlops.ai` | 3 CRDs listed |
| **🧪 Integration** | `helm test mlops-agent-stack -n mlops-agent-stack` | Test pods succeed |

### Expected Test Results Summary

✅ **All pods running**: 6-8 pods in Running state  
✅ **Health endpoints**: All return 200 OK with healthy status  
✅ **CRDs functional**: Can create/read custom resources  
✅ **Metrics collection**: Prometheus collecting MLOps metrics  
✅ **Log aggregation**: Logs visible from all components  
✅ **Unit tests**: All pytest tests pass  
✅ **Integration tests**: Helm tests complete successfully  
✅ **Grafana dashboards**: 4+ dashboards accessible  
✅ **Healing functionality**: Logs show observation and action cycles  

If any test fails, refer to the troubleshooting section above or check the [production operations guide](docs/production-operations.md).

## 📋 Core Components

### Custom Resource Definitions (CRDs)
- **AutoFixPolicy** - Configure automated code fixing behavior
- **InfraHealingRule** - Define infrastructure self-healing rules  
- **CloudConfig** - Abstract cloud provider configurations

### Operators
- **AI Analysis Engine** - Processes metrics and logs using ML models
- **Infrastructure Healer** - Executes automated infrastructure repairs
- **Code Autofix Operator** - Generates and submits code fixes

### Data Collection
- **Prometheus** - Metrics collection and storage
- **FluentBit** - Log aggregation from all cluster components
- **OpenTelemetry** - Distributed tracing and observability

## 📊 Example Usage

### Create an AutoFix Policy

```yaml
apiVersion: mlops.ai/v1
kind: AutoFixPolicy
metadata:
  name: web-app-autofix
spec:
  enabled: true
  repositories:
  - url: "https://github.com/myorg/web-app"
    allowedPaths: ["src/", "lib/"]
    excludedPaths: ["src/secrets/"]
  autoMerge:
    enabled: false
    maxRiskLevel: "low"
  riskAssessment:
    dryRunFirst: true
    maxChangesPerPR: 5
```

### Define Infrastructure Healing Rules

```yaml
apiVersion: mlops.ai/v1
kind: InfraHealingRule
metadata:
  name: production-healing
spec:
  enabled: true
  scope:
    namespaces: ["production"]
    labels:
      tier: "frontend"
  scaling:
    pods:
      enabled: true
      maxReplicas: 20
      scaleUpThreshold: "75%"
  healthChecks:
    pods:
      restartThreshold: 3
      oomKilledAction: "increase-memory"
  safeguards:
    maxActionsPerHour: 5
```

## 📁 Repository Structure

```
mlops-agent-stack/
├── charts/                 # Helm charts for deployment
│   ├── templates/         # Kubernetes manifests
│   └── values.yaml        # Configuration values
├── manifests/             # Raw Kubernetes resources
│   ├── crds/             # Custom Resource Definitions
│   └── policies/         # Example policies
├── operators/             # Custom operators source code
│   ├── ai-engine/        # AI analysis engine
│   ├── infrastructure-healer/  # Self-healing controller
│   └── code-autofix/     # Code fixing operator
├── scripts/              # Deployment and utility scripts
├── docs/                 # Documentation
├── .github/workflows/    # CI/CD pipelines
└── README.md
```

## 🔧 Configuration

### Environment Variables
```bash
# GitHub integration
GITHUB_TOKEN="ghp_your_token_here"

# GitLab integration (optional)
GITLAB_TOKEN="glpat-your_token_here"

# Grafana admin password
GRAFANA_ADMIN_PASSWORD="secure_password"

# Component configuration
DRY_RUN="false"                    # Enable dry-run mode
RECONCILE_INTERVAL="30"            # Reconciliation interval in seconds
MAX_ACTIONS_PER_HOUR="10"          # Rate limiting for actions
```

### Helm Values Customization

See [charts/values.yaml](charts/values.yaml) for all configuration options.

Key settings:
- Component enable/disable flags
- Resource allocations
- Storage configurations
- Security policies
- Monitoring settings

## 🔒 Security Features

### Policy Enforcement
- **Open Policy Agent** integration for fine-grained access control
- **Risk assessment** for all automated actions
- **Approval workflows** for high-risk changes
- **Audit logging** for compliance and forensics

### Authentication & Authorization
- **RBAC** with least-privilege service accounts
- **Service mesh** integration for mTLS
- **Image signing** with Cosign for supply chain security
- **Secret management** with Kubernetes secrets and external secret operators

## 📈 Monitoring & Observability

### Built-in Dashboards
- **AI Metrics** - Model performance and anomaly detection rates
- **Infrastructure Health** - Cluster resource utilization and healing actions
- **Code Quality** - Fix success rates and repository health
- **Security** - Policy violations and access patterns

### Alerting
- **Prometheus AlertManager** integration
- **Slack/Teams** notifications
- **Custom webhook** support
- **Escalation policies** for critical issues

## 🚀 Production Deployment

### Scalability
- **Horizontal Pod Autoscaling** for all components
- **Cluster autoscaling** support
- **Multi-region** deployment capabilities
- **Load balancing** and traffic management

### High Availability
- **Multi-replica** deployments
- **Anti-affinity** rules for pod distribution
- **Persistent storage** for stateful components
- **Backup and recovery** procedures

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup
```bash
# Clone and set up development environment
git clone https://github.com/nishaero/mlops-agent-stack.git
cd mlops-agent-stack

# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest operators/

# Run linting
flake8 operators/
black operators/
```

## 📚 Documentation

- [Quick Start Guide](docs/quick-start.md) - Get up and running in minutes
- [Architecture Documentation](docs/architecture/README.md) - Detailed system design
- [Configuration Guide](docs/configuration.md) - Advanced configuration options
- [Production Guide](docs/production.md) - Production deployment best practices
- [API Reference](docs/api-reference/) - Custom resource specifications

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Kubernetes community for the robust orchestration platform
- Open source AI/ML projects that power our models
- GitOps ecosystem for continuous delivery practices
- Security community for best practices and tooling

## 📞 Support

- 📖 **Documentation**: [docs/](docs/)
- 🐛 **Issues**: [GitHub Issues](https://github.com/nishaero/mlops-agent-stack/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/nishaero/mlops-agent-stack/discussions)
- 📧 **Email**: support@mlops-agent-stack.io

---

**Built with ❤️ by the MLOps community for autonomous, intelligent infrastructure management.**