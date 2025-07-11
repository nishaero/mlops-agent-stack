#!/bin/bash

# MLOps Agent Stack - Deployment Test Script
# This script runs comprehensive tests to verify the deployment is working correctly

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-mlops-agent-stack}"
TIMEOUT="${TIMEOUT:-300}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_TESTS=()

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓ PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_error() {
    echo -e "${RED}[✗ FAIL]${NC} $1"
    ((TESTS_FAILED++))
    FAILED_TESTS+=("$1")
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Test functions
test_prerequisites() {
    log_info "Testing prerequisites..."
    
    # Check kubectl
    if command -v kubectl &> /dev/null; then
        log_success "kubectl is installed"
    else
        log_error "kubectl is not installed"
        return 1
    fi
    
    # Check cluster connectivity
    if kubectl cluster-info &> /dev/null; then
        log_success "Kubernetes cluster is accessible"
    else
        log_error "Cannot connect to Kubernetes cluster"
        return 1
    fi
    
    # Check namespace exists
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_success "Namespace '$NAMESPACE' exists"
    else
        log_error "Namespace '$NAMESPACE' does not exist"
        return 1
    fi
}

test_pod_health() {
    log_info "Testing pod health..."
    
    # Get all pods in namespace
    local pods
    pods=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    
    if [ "$pods" -eq 0 ]; then
        log_error "No pods found in namespace '$NAMESPACE'"
        return 1
    fi
    
    log_success "Found $pods pods in namespace"
    
    # Check if all pods are running
    local running_pods
    running_pods=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
    
    if [ "$running_pods" -eq "$pods" ]; then
        log_success "All $pods pods are in Running state"
    else
        log_error "Only $running_pods out of $pods pods are running"
        kubectl get pods -n "$NAMESPACE"
        return 1
    fi
    
    # Check pod readiness
    local ready_pods=0
    while IFS= read -r line; do
        local ready_status
        ready_status=$(echo "$line" | awk '{print $2}')
        if [[ "$ready_status" == *"/"* ]]; then
            local ready_count
            local total_count
            ready_count=$(echo "$ready_status" | cut -d'/' -f1)
            total_count=$(echo "$ready_status" | cut -d'/' -f2)
            if [ "$ready_count" -eq "$total_count" ]; then
                ((ready_pods++))
            fi
        fi
    done < <(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null)
    
    if [ "$ready_pods" -eq "$pods" ]; then
        log_success "All pods are ready"
    else
        log_error "Only $ready_pods out of $pods pods are ready"
        return 1
    fi
}

test_services() {
    log_info "Testing services..."
    
    local services
    services=$(kubectl get services -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    
    if [ "$services" -eq 0 ]; then
        log_error "No services found in namespace '$NAMESPACE'"
        return 1
    fi
    
    log_success "Found $services services"
    
    # Check if services have endpoints
    local services_with_endpoints=0
    while IFS= read -r service; do
        local endpoints
        endpoints=$(kubectl get endpoints "$service" -n "$NAMESPACE" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null)
        if [ -n "$endpoints" ]; then
            ((services_with_endpoints++))
        fi
    done < <(kubectl get services -n "$NAMESPACE" --no-headers -o custom-columns=":metadata.name" 2>/dev/null)
    
    if [ "$services_with_endpoints" -gt 0 ]; then
        log_success "$services_with_endpoints services have active endpoints"
    else
        log_error "No services have active endpoints"
        return 1
    fi
}

test_crds() {
    log_info "Testing Custom Resource Definitions..."
    
    local expected_crds=("autofixpolicies.mlops.ai" "infrahealingrules.mlops.ai" "cloudconfigs.mlops.ai")
    local found_crds=0
    
    for crd in "${expected_crds[@]}"; do
        if kubectl get crd "$crd" &> /dev/null; then
            log_success "CRD '$crd' is installed"
            ((found_crds++))
        else
            log_error "CRD '$crd' is not installed"
        fi
    done
    
    if [ "$found_crds" -eq "${#expected_crds[@]}" ]; then
        log_success "All required CRDs are installed"
    else
        return 1
    fi
}

test_health_endpoints() {
    log_info "Testing health endpoints..."
    
    local components=("ai-engine" "infrastructure-healer" "code-autofix")
    local base_port=8080
    
    for i in "${!components[@]}"; do
        local component="${components[$i]}"
        local port=$((base_port + i))
        local service="mlops-agent-stack-$component"
        
        # Check if service exists
        if ! kubectl get service "$service" -n "$NAMESPACE" &> /dev/null; then
            log_error "Service '$service' not found"
            continue
        fi
        
        # Start port-forward in background
        kubectl port-forward "svc/$service" "$port:8080" -n "$NAMESPACE" > /dev/null 2>&1 &
        local pf_pid=$!
        
        # Wait a moment for port-forward to establish
        sleep 3
        
        # Test health endpoint
        if curl -f -s "http://localhost:$port/health" > /dev/null 2>&1; then
            log_success "$component health endpoint is responding"
        else
            log_error "$component health endpoint is not responding"
        fi
        
        # Clean up port-forward
        kill $pf_pid &> /dev/null || true
        sleep 1
    done
}

test_metrics_collection() {
    log_info "Testing metrics collection..."
    
    # Check if Prometheus service exists
    if ! kubectl get service prometheus-server -n "$NAMESPACE" &> /dev/null; then
        log_error "Prometheus server service not found"
        return 1
    fi
    
    # Start port-forward for Prometheus
    kubectl port-forward svc/prometheus-server 9090:80 -n "$NAMESPACE" > /dev/null 2>&1 &
    local pf_pid=$!
    
    # Wait for port-forward
    sleep 5
    
    # Test Prometheus API
    if curl -f -s "http://localhost:9090/api/v1/query?query=up" > /dev/null 2>&1; then
        log_success "Prometheus is collecting metrics"
    else
        log_error "Prometheus is not responding"
    fi
    
    # Clean up
    kill $pf_pid &> /dev/null || true
    sleep 1
}

test_logs() {
    log_info "Testing log collection..."
    
    local components_with_logs=0
    local components=("ai-engine" "infrastructure-healer" "code-autofix")
    
    for component in "${components[@]}"; do
        local logs
        logs=$(kubectl logs -l "component=$component" -n "$NAMESPACE" --tail=5 2>/dev/null)
        if [ -n "$logs" ]; then
            ((components_with_logs++))
        fi
    done
    
    if [ "$components_with_logs" -gt 0 ]; then
        log_success "$components_with_logs components are generating logs"
    else
        log_error "No components are generating logs"
        return 1
    fi
}

test_basic_functionality() {
    log_info "Testing basic functionality..."
    
    # Create a test AutoFixPolicy
    kubectl apply -f - << EOF > /dev/null 2>&1
apiVersion: mlops.ai/v1
kind: AutoFixPolicy
metadata:
  name: test-policy-$(date +%s)
  namespace: $NAMESPACE
spec:
  enabled: false
  repositories: []
  autoMerge:
    enabled: false
EOF
    
    if [ $? -eq 0 ]; then
        log_success "Can create custom resources"
    else
        log_error "Cannot create custom resources"
        return 1
    fi
    
    # Clean up test policy
    kubectl delete autofixpolicies -l "test=true" -n "$NAMESPACE" &> /dev/null || true
}

# Run integration tests if available
test_integration() {
    log_info "Testing integration..."
    
    # Check if Helm test exists
    if helm test mlops-agent-stack -n "$NAMESPACE" --timeout="${TIMEOUT}s" &> /dev/null; then
        log_success "Helm integration tests passed"
    else
        log_error "Helm integration tests failed"
        return 1
    fi
}

# Main test execution
run_all_tests() {
    log_info "Starting MLOps Agent Stack deployment tests..."
    log_info "Namespace: $NAMESPACE"
    log_info "Timeout: ${TIMEOUT}s"
    echo ""
    
    # Run all tests
    test_prerequisites || true
    test_pod_health || true
    test_services || true
    test_crds || true
    test_health_endpoints || true
    test_metrics_collection || true
    test_logs || true
    test_basic_functionality || true
    test_integration || true
    
    echo ""
    log_info "Test Summary:"
    echo "  Tests Passed: $TESTS_PASSED"
    echo "  Tests Failed: $TESTS_FAILED"
    
    if [ "$TESTS_FAILED" -eq 0 ]; then
        echo ""
        log_success "🎉 All tests passed! Your MLOps Agent Stack deployment is working correctly."
        echo ""
        log_info "Next steps:"
        echo "  - Access Grafana: kubectl port-forward svc/grafana 3000:80 -n $NAMESPACE"
        echo "  - View metrics: kubectl port-forward svc/prometheus-server 9090:80 -n $NAMESPACE"
        echo "  - Check logs: kubectl logs -f -l app.kubernetes.io/name=mlops-agent-stack -n $NAMESPACE"
        echo ""
        return 0
    else
        echo ""
        log_error "❌ $TESTS_FAILED test(s) failed. Please check the following:"
        for test in "${FAILED_TESTS[@]}"; do
            echo "  - $test"
        done
        echo ""
        log_info "Troubleshooting tips:"
        echo "  - Check pod status: kubectl get pods -n $NAMESPACE"
        echo "  - Check events: kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp'"
        echo "  - Check logs: kubectl logs -l app.kubernetes.io/name=mlops-agent-stack -n $NAMESPACE"
        echo ""
        return 1
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --namespace NAMESPACE    Kubernetes namespace (default: mlops-agent-stack)"
            echo "  --timeout TIMEOUT       Test timeout in seconds (default: 300)"
            echo "  --help                   Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run tests
run_all_tests