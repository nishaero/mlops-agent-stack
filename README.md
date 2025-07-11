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
- Kubernetes cluster (v1.24+)
- Helm 3.12+
- kubectl configured
- 8GB+ RAM, 4+ CPU cores

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