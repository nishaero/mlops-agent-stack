#!/bin/bash

# MLOps Agent Stack Deployment Script
# This script deploys the complete MLOps Agent Stack to a Kubernetes cluster

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-mlops-agent-stack}"
RELEASE_NAME="${RELEASE_NAME:-mlops-agent-stack}"
CHART_PATH="${CHART_PATH:-./charts}"
VALUES_FILE="${VALUES_FILE:-./charts/values.yaml}"
DRY_RUN="${DRY_RUN:-false}"
SKIP_CRD_INSTALL="${SKIP_CRD_INSTALL:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if kubectl is installed and configured
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check if helm is installed
    if ! command -v helm &> /dev/null; then
        log_error "helm is not installed or not in PATH"
        exit 1
    fi
    
    # Check if we can connect to Kubernetes cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Please check your kubeconfig."
        exit 1
    fi
    
    # Check Kubernetes version
    K8S_VERSION=$(kubectl version --client=false -o json | jq -r '.serverVersion.gitVersion' | sed 's/v//')
    REQUIRED_VERSION="1.24.0"
    if ! printf '%s\n%s\n' "$REQUIRED_VERSION" "$K8S_VERSION" | sort -V -C; then
        log_warning "Kubernetes version $K8S_VERSION detected. Minimum required version is $REQUIRED_VERSION"
    fi
    
    log_success "Prerequisites check completed"
}

# Install Custom Resource Definitions
install_crds() {
    if [ "$SKIP_CRD_INSTALL" = "true" ]; then
        log_info "Skipping CRD installation"
        return
    fi
    
    log_info "Installing Custom Resource Definitions..."
    
    kubectl apply -f manifests/crds/autofix-policy.yaml
    kubectl apply -f manifests/crds/infra-healing-rule.yaml
    kubectl apply -f manifests/crds/cloud-config.yaml
    
    # Wait for CRDs to be established
    log_info "Waiting for CRDs to be established..."
    kubectl wait --for condition=established --timeout=60s crd/autofixpolicies.mlops.ai
    kubectl wait --for condition=established --timeout=60s crd/infrahealingrules.mlops.ai
    kubectl wait --for condition=established --timeout=60s crd/cloudconfigs.mlops.ai
    
    log_success "CRDs installed successfully"
}

# Create namespace if it doesn't exist
create_namespace() {
    log_info "Creating namespace '$NAMESPACE'..."
    
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_info "Namespace '$NAMESPACE' already exists"
    else
        kubectl create namespace "$NAMESPACE"
        log_success "Namespace '$NAMESPACE' created"
    fi
}

# Create secrets
create_secrets() {
    log_info "Setting up secrets..."
    
    # GitHub token secret (if provided)
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        kubectl create secret generic github-token \
            --from-literal=token="$GITHUB_TOKEN" \
            --namespace="$NAMESPACE" \
            --dry-run=client -o yaml | kubectl apply -f -
        log_success "GitHub token secret created"
    else
        log_warning "GITHUB_TOKEN not provided. Code autofix functionality may be limited."
    fi
    
    # GitLab token secret (if provided)
    if [ -n "${GITLAB_TOKEN:-}" ]; then
        kubectl create secret generic gitlab-token \
            --from-literal=token="$GITLAB_TOKEN" \
            --namespace="$NAMESPACE" \
            --dry-run=client -o yaml | kubectl apply -f -
        log_success "GitLab token secret created"
    fi
    
    # Grafana admin password
    if [ -n "${GRAFANA_ADMIN_PASSWORD:-}" ]; then
        kubectl create secret generic grafana-admin \
            --from-literal=password="$GRAFANA_ADMIN_PASSWORD" \
            --namespace="$NAMESPACE" \
            --dry-run=client -o yaml | kubectl apply -f -
        log_success "Grafana admin secret created"
    else
        # Generate random password
        GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 12)
        kubectl create secret generic grafana-admin \
            --from-literal=password="$GRAFANA_ADMIN_PASSWORD" \
            --namespace="$NAMESPACE" \
            --dry-run=client -o yaml | kubectl apply -f -
        log_success "Grafana admin secret created with password: $GRAFANA_ADMIN_PASSWORD"
    fi
}

# Install Helm dependencies
install_helm_dependencies() {
    log_info "Installing Helm dependencies..."
    
    if [ ! -f "$CHART_PATH/Chart.lock" ] || [ "$CHART_PATH/Chart.yaml" -nt "$CHART_PATH/Chart.lock" ]; then
        helm dependency update "$CHART_PATH"
        log_success "Helm dependencies updated"
    else
        log_info "Helm dependencies are up to date"
    fi
}

# Deploy the stack
deploy_stack() {
    log_info "Deploying MLOps Agent Stack..."
    
    # Prepare helm command
    HELM_CMD="helm upgrade --install $RELEASE_NAME $CHART_PATH"
    HELM_CMD="$HELM_CMD --namespace $NAMESPACE"
    HELM_CMD="$HELM_CMD --values $VALUES_FILE"
    HELM_CMD="$HELM_CMD --timeout 600s"
    HELM_CMD="$HELM_CMD --wait"
    
    # Add dry-run flag if specified
    if [ "$DRY_RUN" = "true" ]; then
        HELM_CMD="$HELM_CMD --dry-run"
        log_info "Running in dry-run mode"
    fi
    
    # Add any additional Helm values
    if [ -n "${IMAGE_TAG:-}" ]; then
        HELM_CMD="$HELM_CMD --set aiEngine.image.tag=$IMAGE_TAG"
        HELM_CMD="$HELM_CMD --set infrastructureHealer.image.tag=$IMAGE_TAG"
        HELM_CMD="$HELM_CMD --set codeAutofix.image.tag=$IMAGE_TAG"
    fi
    
    if [ -n "${IMAGE_REGISTRY:-}" ]; then
        HELM_CMD="$HELM_CMD --set global.imageRegistry=$IMAGE_REGISTRY"
    fi
    
    # Execute helm command
    eval "$HELM_CMD"
    
    if [ "$DRY_RUN" = "true" ]; then
        log_success "Dry-run completed successfully"
    else
        log_success "MLOps Agent Stack deployed successfully"
    fi
}

# Verify deployment
verify_deployment() {
    if [ "$DRY_RUN" = "true" ]; then
        return
    fi
    
    log_info "Verifying deployment..."
    
    # Check if all pods are running
    log_info "Checking pod status..."
    kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE_NAME"
    
    # Wait for pods to be ready
    kubectl wait --for=condition=Ready pods -l "app.kubernetes.io/instance=$RELEASE_NAME" -n "$NAMESPACE" --timeout=300s
    
    # Check services
    log_info "Checking services..."
    kubectl get services -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE_NAME"
    
    # Check custom resources
    log_info "Checking custom resources..."
    kubectl get autofixpolicies,infrahealingrules,cloudconfigs --all-namespaces
    
    log_success "Deployment verification completed"
}

# Install example policies
install_example_policies() {
    if [ "$DRY_RUN" = "true" ]; then
        return
    fi
    
    log_info "Installing example policies..."
    
    kubectl apply -f manifests/policies/ -n "$NAMESPACE"
    
    log_success "Example policies installed"
}

# Display access information
display_access_info() {
    if [ "$DRY_RUN" = "true" ]; then
        return
    fi
    
    log_info "Access Information:"
    echo ""
    
    # Get LoadBalancer/NodePort services
    SERVICES=$(kubectl get svc -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}')
    
    for service in $SERVICES; do
        SERVICE_TYPE=$(kubectl get svc "$service" -n "$NAMESPACE" -o jsonpath='{.spec.type}')
        
        if [ "$SERVICE_TYPE" = "LoadBalancer" ]; then
            EXTERNAL_IP=$(kubectl get svc "$service" -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
            if [ -n "$EXTERNAL_IP" ]; then
                PORT=$(kubectl get svc "$service" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].port}')
                echo "  $service: http://$EXTERNAL_IP:$PORT"
            fi
        elif [ "$SERVICE_TYPE" = "NodePort" ]; then
            NODE_PORT=$(kubectl get svc "$service" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].nodePort}')
            NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')
            if [ -z "$NODE_IP" ]; then
                NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
            fi
            echo "  $service: http://$NODE_IP:$NODE_PORT"
        fi
    done
    
    echo ""
    log_info "To check the status of your deployment:"
    echo "  kubectl get pods -n $NAMESPACE"
    echo "  kubectl logs -f deployment/mlops-agent-stack-ai-engine -n $NAMESPACE"
    echo ""
    
    if [ -n "${GRAFANA_ADMIN_PASSWORD:-}" ]; then
        log_info "Grafana admin password: $GRAFANA_ADMIN_PASSWORD"
    fi
}

# Cleanup function
cleanup() {
    log_info "To uninstall the MLOps Agent Stack:"
    echo "  helm uninstall $RELEASE_NAME -n $NAMESPACE"
    echo "  kubectl delete namespace $NAMESPACE"
    echo "  kubectl delete crd autofixpolicies.mlops.ai infrahealingrules.mlops.ai cloudconfigs.mlops.ai"
}

# Print usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --namespace NAMESPACE     Kubernetes namespace (default: mlops-agent-stack)"
    echo "  --release-name NAME       Helm release name (default: mlops-agent-stack)"
    echo "  --chart-path PATH         Path to Helm chart (default: ./charts)"
    echo "  --values-file FILE        Helm values file (default: ./charts/values.yaml)"
    echo "  --dry-run                 Perform a dry-run without making changes"
    echo "  --skip-crd-install        Skip CRD installation"
    echo "  --image-tag TAG           Override image tag for all components"
    echo "  --image-registry REGISTRY Override image registry"
    echo "  --help                    Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  GITHUB_TOKEN              GitHub personal access token"
    echo "  GITLAB_TOKEN              GitLab personal access token"
    echo "  GRAFANA_ADMIN_PASSWORD    Grafana admin password"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Deploy with default settings"
    echo "  $0 --dry-run                         # Perform dry-run"
    echo "  $0 --namespace production             # Deploy to production namespace"
    echo "  GITHUB_TOKEN=\$TOKEN $0               # Deploy with GitHub integration"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --release-name)
            RELEASE_NAME="$2"
            shift 2
            ;;
        --chart-path)
            CHART_PATH="$2"
            shift 2
            ;;
        --values-file)
            VALUES_FILE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --skip-crd-install)
            SKIP_CRD_INSTALL="true"
            shift
            ;;
        --image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --image-registry)
            IMAGE_REGISTRY="$2"
            shift 2
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    log_info "Starting MLOps Agent Stack deployment..."
    log_info "Namespace: $NAMESPACE"
    log_info "Release Name: $RELEASE_NAME"
    log_info "Chart Path: $CHART_PATH"
    log_info "Values File: $VALUES_FILE"
    echo ""
    
    check_prerequisites
    install_crds
    create_namespace
    create_secrets
    install_helm_dependencies
    deploy_stack
    verify_deployment
    install_example_policies
    display_access_info
    
    echo ""
    log_success "MLOps Agent Stack deployment completed successfully!"
    echo ""
    cleanup
}

# Trap to handle script interruption
trap 'log_error "Script interrupted"; exit 1' INT TERM

# Run main function
main "$@"