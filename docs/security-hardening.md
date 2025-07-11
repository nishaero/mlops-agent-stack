# MLOps Agent Stack - Security Hardening Guide

## 🔒 Security Overview

This guide provides comprehensive security hardening recommendations for production deployments of the MLOps Agent Stack. It covers defense-in-depth strategies across all layers of the stack.

## 🛡 Pod Security Standards

### Restricted Pod Security Policy

```yaml
# Enable the most restrictive Pod Security Standards
security:
  podSecurityStandards:
    enabled: true
    enforce: "restricted"
    audit: "restricted"
    warn: "restricted"
    enforceVersion: "v1.28"
```

### Security Context Configuration

```yaml
# Pod-level security context
security:
  podSecurityContext:
    enabled: true
    runAsNonRoot: true
    runAsUser: 65534      # nobody user
    runAsGroup: 65534     # nobody group
    fsGroup: 65534
    fsGroupChangePolicy: "OnRootMismatch"

# Container-level security context
  containerSecurityContext:
    enabled: true
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: true
    runAsNonRoot: true
    runAsUser: 65534
    capabilities:
      drop:
        - "ALL"
    seccompProfile:
      type: RuntimeDefault
    seLinuxOptions:
      level: "s0:c123,c456"
```

## 🌐 Network Security

### Network Policies

#### Default Deny All Traffic
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
```

#### Allow Specific Communication
```yaml
security:
  networkPolicies:
    enabled: true
    defaultDeny: true
    policies:
      - name: "ai-engine-communication"
        podSelector:
          matchLabels:
            component: ai-engine
        ingress:
          - from:
            - podSelector:
                matchLabels:
                  component: infrastructure-healer
            ports:
            - protocol: TCP
              port: 8080
```

### Service Mesh Security (Optional)

```yaml
networking:
  istio:
    enabled: true
    mtls:
      mode: STRICT
    authorizationPolicies:
      enabled: true
    telemetry:
      v2: true
    security:
      certificateRotation: "24h"
```

## 🔐 Secrets Management

### Kubernetes Secrets Best Practices

#### Enable Secret Encryption at Rest
```yaml
# etcd encryption configuration
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
- resources:
  - secrets
  providers:
  - aescbc:
      keys:
      - name: key1
        secret: <base64-encoded-32-byte-key>
  - identity: {}
```

#### Use External Secret Management
```yaml
# External Secrets Operator configuration
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "https://vault.company.com"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "mlops-role"
```

### Secret Rotation

```bash
#!/bin/bash
# Automated secret rotation script

# GitHub token rotation
kubectl create secret generic github-token-new \
  --from-literal=token="$NEW_GITHUB_TOKEN" \
  --namespace=mlops-agent-stack

kubectl patch deployment mlops-agent-stack-code-autofix \
  --patch '{"spec":{"template":{"spec":{"containers":[{"name":"code-autofix","env":[{"name":"GITHUB_TOKEN","valueFrom":{"secretKeyRef":{"name":"github-token-new","key":"token"}}}]}]}}}}'

kubectl delete secret github-token
kubectl rename secret github-token-new github-token
```

## 🔍 Image Security

### Container Image Scanning

```yaml
security:
  imageScanning:
    enabled: true
    scanner: "trivy"
    failOnHigh: true
    failOnCritical: true
    scanSchedule: "0 2 * * *"  # Daily at 2 AM
    allowedVulnerabilities:
      - "CVE-2021-12345"  # Documented exception
```

### Image Signing and Verification

```yaml
# Cosign image verification
security:
  imageVerification:
    enabled: true
    publicKey: |
      -----BEGIN PUBLIC KEY-----
      MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...
      -----END PUBLIC KEY-----
    requiredAnnotations:
      - "io.cosign.signature"
```

### Distroless Base Images

```dockerfile
# Use distroless images for minimal attack surface
FROM gcr.io/distroless/python3-debian11

# Copy application
COPY --from=builder /app /app
COPY --from=builder /models /models

# Run as non-root user
USER 65534:65534

ENTRYPOINT ["/app/main"]
```

## 🔒 Access Control

### RBAC Configuration

```yaml
# Principle of least privilege
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ai-engine
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ai-engine-role
rules:
- apiGroups: [""]
  resources: ["configmaps", "secrets"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["metrics.k8s.io"]
  resources: ["*"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ai-engine-binding
subjects:
- kind: ServiceAccount
  name: ai-engine
roleRef:
  kind: Role
  name: ai-engine-role
  apiGroup: rbac.authorization.k8s.io
```

### OPA Gatekeeper Policies

```yaml
# Require security labels
apiVersion: templates.gatekeeper.sh/v1beta1
kind: ConstraintTemplate
metadata:
  name: k8srequiredsecuritylabels
spec:
  crd:
    spec:
      names:
        kind: K8sRequiredSecurityLabels
      validation:
        type: object
        properties:
          labels:
            type: array
            items:
              type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequiredsecuritylabels
        
        violation[{"msg": msg}] {
          required := input.parameters.labels
          provided := input.review.object.metadata.labels
          missing := required[_]
          not provided[missing]
          msg := sprintf("Missing required security label: %v", [missing])
        }
```

## 🛡 Runtime Security

### Pod Security Admission

```yaml
# Namespace configuration for Pod Security Admission
apiVersion: v1
kind: Namespace
metadata:
  name: mlops-agent-stack
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
  annotations:
    pod-security.kubernetes.io/enforce-version: v1.28
```

### Security Monitoring

```yaml
# Falco runtime security monitoring
apiVersion: v1
kind: ConfigMap
metadata:
  name: falco-rules
data:
  mlops_rules.yaml: |
    - rule: Suspicious AI Model Access
      desc: Detect suspicious access to AI model files
      condition: >
        open_read and
        container and
        fd.name contains "/models/" and
        not proc.name in (python, pytorch, tensorflow)
      output: >
        Suspicious AI model access
        (command=%proc.cmdline file=%fd.name)
      priority: WARNING
    
    - rule: Unusual Network Connection from AI Engine
      desc: Detect unusual outbound connections from AI Engine
      condition: >
        outbound and
        container and
        k8s.pod.label[component] = "ai-engine" and
        not fd.sip in (prometheus_ips, loki_ips, api_server_ips)
      output: >
        Unusual network connection from AI Engine
        (connection=%fd.name command=%proc.cmdline)
      priority: WARNING
```

## 🔐 Data Protection

### Encryption Configuration

#### At-Rest Encryption
```yaml
# Enable encryption for persistent volumes
security:
  encryption:
    atRest:
      enabled: true
      provider: "aws-kms"  # or "gcp-kms", "azure-kv"
      keyId: "arn:aws:kms:us-west-2:123456789:key/12345678-1234-1234-1234-123456789012"
```

#### In-Transit Encryption
```yaml
# TLS configuration
security:
  tls:
    enabled: true
    minVersion: "1.2"
    cipherSuites:
      - "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384"
      - "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305"
    certificates:
      aiEngine:
        secretName: "ai-engine-tls"
        dnsNames:
          - "ai-engine.mlops-agent-stack.svc.cluster.local"
```

### Data Loss Prevention

```yaml
# DLP policies for sensitive data
security:
  dataLossPrevention:
    enabled: true
    policies:
      - name: "prevent-credential-exposure"
        pattern: "password|secret|token|key"
        action: "block"
        severity: "high"
      - name: "prevent-pii-exposure"
        pattern: "\\b\\d{3}-\\d{2}-\\d{4}\\b"  # SSN pattern
        action: "alert"
        severity: "medium"
```

## 🔍 Security Auditing

### Audit Logging

```yaml
# Kubernetes audit policy
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
- level: Metadata
  namespaces: ["mlops-agent-stack"]
  resources:
  - group: ""
    resources: ["secrets", "configmaps"]
  - group: "apps"
    resources: ["deployments", "statefulsets"]
  - group: "mlops.ai"
    resources: ["*"]
```

### Security Scanning Schedule

```yaml
security:
  scanning:
    schedule:
      vulnerabilities: "0 2 * * *"    # Daily at 2 AM
      configurations: "0 3 * * 0"     # Weekly on Sunday at 3 AM
      compliance: "0 4 1 * *"         # Monthly on 1st at 4 AM
    
    compliance:
      frameworks:
        - "CIS"
        - "NIST"
        - "SOC2"
        - "PCI-DSS"
```

## 🚨 Incident Response

### Security Incident Playbook

1. **Detection**: Automated alerts via Falco, OPA violations, or monitoring
2. **Assessment**: Determine scope and impact
3. **Containment**: Isolate affected components
4. **Investigation**: Collect logs and evidence
5. **Remediation**: Apply fixes and patches
6. **Recovery**: Restore services safely
7. **Lessons Learned**: Document and improve

### Emergency Response Commands

```bash
# Emergency security lockdown
kubectl patch networkpolicy default-allow-all --patch '{"spec":{"podSelector":{},"policyTypes":["Ingress","Egress"]}}'

# Isolate suspicious pod
kubectl label pod suspicious-pod quarantine=true
kubectl patch networkpolicy quarantine --patch '{"spec":{"podSelector":{"matchLabels":{"quarantine":"true"}},"policyTypes":["Ingress","Egress"]}}'

# Emergency secret rotation
kubectl delete secret sensitive-secret
kubectl create secret generic sensitive-secret --from-literal=key="new-secure-value"
kubectl rollout restart deployment/affected-deployment
```

## 📋 Security Checklist

### Pre-Deployment Security Checklist

- [ ] Pod Security Standards configured to "restricted"
- [ ] All containers run as non-root
- [ ] Read-only root filesystems enabled
- [ ] Network policies implemented with default deny
- [ ] Secrets encrypted at rest
- [ ] Container images scanned for vulnerabilities
- [ ] RBAC follows principle of least privilege
- [ ] TLS enabled for all communications
- [ ] Audit logging configured
- [ ] Security monitoring deployed (Falco)
- [ ] Backup encryption verified
- [ ] Incident response procedures documented

### Regular Security Maintenance

- [ ] Weekly vulnerability scans
- [ ] Monthly access reviews
- [ ] Quarterly penetration testing
- [ ] Annual security architecture review
- [ ] Continuous compliance monitoring
- [ ] Regular security training for team

## 📚 Security Resources

### Standards and Frameworks
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [CIS Kubernetes Benchmark](https://www.cisecurity.org/benchmark/kubernetes)
- [OWASP Container Security Top 10](https://owasp.org/www-project-container-security-top-10/)
- [NSA Kubernetes Hardening Guide](https://media.defense.gov/2022/Aug/29/2003066362/-1/-1/0/CTR_KUBERNETES_HARDENING_GUIDANCE_1.2_20220829.PDF)

### Tools and Resources
- [Falco Runtime Security](https://falco.org/)
- [OPA Gatekeeper](https://open-policy-agent.github.io/gatekeeper/)
- [Trivy Vulnerability Scanner](https://trivy.dev/)
- [Cosign Image Signing](https://sigstore.dev/)
- [Kubernetes Security Best Practices](https://kubernetes.io/docs/concepts/security/)

### Emergency Contacts
- **Security Team**: `security@company.com`
- **CISO Office**: `ciso@company.com`
- **24/7 Security Hotline**: `+1-555-SECURITY`