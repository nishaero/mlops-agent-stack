#!/usr/bin/env python3
"""
AI Analysis Engine for MLOps Agent Stack

This component handles:
- Anomaly detection in metrics
- Log analysis and error classification
- Root cause analysis using graph neural networks
- Integration with Kubernetes APIs and monitoring systems
"""

import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import aiohttp
import numpy as np
import torch
import torch.nn as nn
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from prometheus_client import start_http_server, Counter, Histogram, Gauge

# Metrics
ANOMALIES_DETECTED = Counter('mlops_anomalies_detected_total', 'Total anomalies detected', ['type', 'severity'])
ANALYSIS_DURATION = Histogram('mlops_analysis_duration_seconds', 'Time spent analyzing data', ['model_type'])
ACTIVE_MODELS = Gauge('mlops_active_models', 'Number of active AI models', ['model_type'])

logger = logging.getLogger(__name__)

@dataclass
class AnomalyResult:
    """Result of anomaly detection analysis"""
    timestamp: datetime
    metric_name: str
    severity: str  # low, medium, high, critical
    confidence: float
    predicted_value: float
    actual_value: float
    context: Dict[str, Any]

@dataclass
class LogAnalysisResult:
    """Result of log analysis"""
    timestamp: datetime
    log_level: str
    error_category: str
    confidence: float
    suggested_action: str
    related_pods: List[str]
    root_cause: Optional[str] = None

class AnomalyDetectionModel(nn.Module):
    """LSTM-based anomaly detection model"""
    
    def __init__(self, input_size: int, hidden_size: int = 64, num_layers: int = 2):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.dropout = nn.Dropout(0.2)
        self.fc = nn.Linear(hidden_size, 1)
        
    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
        
        out, _ = self.lstm(x, (h0, c0))
        out = self.dropout(out[:, -1, :])
        out = self.fc(out)
        return out

class LogAnalysisModel(nn.Module):
    """BERT-based log analysis model"""
    
    def __init__(self, vocab_size: int, embed_dim: int = 256, num_classes: int = 10):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.transformer = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(embed_dim, nhead=8, batch_first=True),
            num_layers=6
        )
        self.classifier = nn.Linear(embed_dim, num_classes)
        
    def forward(self, x):
        x = self.embedding(x)
        x = self.transformer(x)
        x = x.mean(dim=1)  # Global average pooling
        return self.classifier(x)

class AIAnalysisEngine:
    """Main AI Analysis Engine"""
    
    def __init__(self):
        self.prometheus_url = os.getenv('PROMETHEUS_URL', 'http://prometheus:9090')
        self.loki_url = os.getenv('LOKI_URL', 'http://loki:3100')
        self.models_path = os.getenv('MODELS_PATH', '/models')
        
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        
        self.k8s_client = client.ApiClient()
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.custom_api = client.CustomObjectsApi()
        
        # Load AI models
        self.anomaly_model = None
        self.log_model = None
        self.load_models()
        
        # Analysis state
        self.last_analysis = {}
        self.analysis_interval = 30  # seconds
        
    def load_models(self):
        """Load pre-trained AI models"""
        try:
            # Load anomaly detection model
            anomaly_path = f"{self.models_path}/anomaly-lstm/model.pt"
            if os.path.exists(anomaly_path):
                self.anomaly_model = AnomalyDetectionModel(input_size=5)
                self.anomaly_model.load_state_dict(torch.load(anomaly_path, map_location='cpu'))
                self.anomaly_model.eval()
                ACTIVE_MODELS.labels(model_type='anomaly').set(1)
                logger.info("Loaded anomaly detection model")
            
            # Load log analysis model
            log_path = f"{self.models_path}/log-bert/model.pt"
            if os.path.exists(log_path):
                self.log_model = LogAnalysisModel(vocab_size=10000)
                self.log_model.load_state_dict(torch.load(log_path, map_location='cpu'))
                self.log_model.eval()
                ACTIVE_MODELS.labels(model_type='log_analysis').set(1)
                logger.info("Loaded log analysis model")
                
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
    
    async def fetch_metrics(self, query: str, start_time: datetime, end_time: datetime) -> Dict:
        """Fetch metrics from Prometheus"""
        params = {
            'query': query,
            'start': start_time.isoformat(),
            'end': end_time.isoformat(),
            'step': '30s'
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.prometheus_url}/api/v1/query_range"
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    return data.get('data', {}).get('result', [])
            except Exception as e:
                logger.error(f"Failed to fetch metrics: {e}")
                return []
    
    async def fetch_logs(self, query: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Fetch logs from Loki"""
        params = {
            'query': query,
            'start': int(start_time.timestamp() * 1e9),
            'end': int(end_time.timestamp() * 1e9),
            'limit': 1000
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.loki_url}/loki/api/v1/query_range"
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    streams = data.get('data', {}).get('result', [])
                    logs = []
                    for stream in streams:
                        for entry in stream.get('values', []):
                            logs.append({
                                'timestamp': entry[0],
                                'message': entry[1],
                                'labels': stream.get('stream', {})
                            })
                    return logs
            except Exception as e:
                logger.error(f"Failed to fetch logs: {e}")
                return []
    
    def analyze_anomalies(self, metrics_data: List[Dict]) -> List[AnomalyResult]:
        """Analyze metrics for anomalies using LSTM model"""
        if not self.anomaly_model or not metrics_data:
            return []
        
        results = []
        
        with ANALYSIS_DURATION.labels(model_type='anomaly').time():
            for metric in metrics_data:
                try:
                    values = [float(point[1]) for point in metric.get('values', [])]
                    if len(values) < 10:  # Need minimum data points
                        continue
                    
                    # Prepare data for LSTM
                    sequence_length = min(10, len(values))
                    input_data = []
                    
                    for i in range(len(values) - sequence_length):
                        sequence = values[i:i+sequence_length]
                        # Add statistical features
                        features = [
                            np.mean(sequence),
                            np.std(sequence),
                            np.min(sequence),
                            np.max(sequence),
                            sequence[-1]  # Current value
                        ]
                        input_data.append(features)
                    
                    if not input_data:
                        continue
                    
                    # Convert to tensor and predict
                    input_tensor = torch.FloatTensor(input_data).unsqueeze(0)
                    with torch.no_grad():
                        predictions = self.anomaly_model(input_tensor)
                    
                    # Analyze predictions for anomalies
                    for i, pred in enumerate(predictions.squeeze()):
                        actual = values[sequence_length + i]
                        diff = abs(pred.item() - actual)
                        confidence = min(diff / (actual + 1e-6), 1.0)
                        
                        if confidence > 0.7:  # High confidence anomaly
                            severity = 'critical' if confidence > 0.9 else 'high' if confidence > 0.8 else 'medium'
                            
                            result = AnomalyResult(
                                timestamp=datetime.now(),
                                metric_name=metric.get('metric', {}).get('__name__', 'unknown'),
                                severity=severity,
                                confidence=confidence,
                                predicted_value=pred.item(),
                                actual_value=actual,
                                context={
                                    'labels': metric.get('metric', {}),
                                    'sequence_analysis': {
                                        'mean': np.mean(values),
                                        'std': np.std(values),
                                        'trend': 'increasing' if values[-1] > values[0] else 'decreasing'
                                    }
                                }
                            )
                            results.append(result)
                            ANOMALIES_DETECTED.labels(type='metric', severity=severity).inc()
                            
                except Exception as e:
                    logger.error(f"Error analyzing metric {metric}: {e}")
        
        return results
    
    def analyze_logs(self, logs_data: List[Dict]) -> List[LogAnalysisResult]:
        """Analyze logs for errors and issues"""
        if not self.log_model or not logs_data:
            return []
        
        results = []
        error_categories = [
            'CrashLoopBackOff', 'OOMKilled', 'ImagePullBackOff', 'NetworkError',
            'DatabaseConnection', 'AuthenticationFailure', 'ConfigurationError',
            'PermissionDenied', 'ResourceQuotaExceeded', 'Other'
        ]
        
        with ANALYSIS_DURATION.labels(model_type='log_analysis').time():
            for log_entry in logs_data:
                try:
                    message = log_entry.get('message', '')
                    labels = log_entry.get('labels', {})
                    
                    # Simple keyword-based classification for demo
                    # In production, use the trained BERT model
                    error_category = 'Other'
                    confidence = 0.0
                    suggested_action = 'Monitor and investigate'
                    
                    if any(keyword in message.lower() for keyword in ['oom', 'out of memory']):
                        error_category = 'OOMKilled'
                        confidence = 0.9
                        suggested_action = 'Increase memory limits or optimize memory usage'
                    elif any(keyword in message.lower() for keyword in ['crashloopbackoff', 'crash loop']):
                        error_category = 'CrashLoopBackOff'
                        confidence = 0.85
                        suggested_action = 'Check application startup logic and dependencies'
                    elif any(keyword in message.lower() for keyword in ['imagepullbackoff', 'image pull']):
                        error_category = 'ImagePullBackOff'
                        confidence = 0.8
                        suggested_action = 'Verify image name and registry credentials'
                    elif any(keyword in message.lower() for keyword in ['connection refused', 'network']):
                        error_category = 'NetworkError'
                        confidence = 0.75
                        suggested_action = 'Check network policies and service configurations'
                    
                    if confidence > 0.5:  # Only report significant errors
                        result = LogAnalysisResult(
                            timestamp=datetime.now(),
                            log_level=self.extract_log_level(message),
                            error_category=error_category,
                            confidence=confidence,
                            suggested_action=suggested_action,
                            related_pods=[labels.get('pod', 'unknown')]
                        )
                        results.append(result)
                        ANOMALIES_DETECTED.labels(type='log', severity=error_category).inc()
                        
                except Exception as e:
                    logger.error(f"Error analyzing log {log_entry}: {e}")
        
        return results
    
    def extract_log_level(self, message: str) -> str:
        """Extract log level from message"""
        message_lower = message.lower()
        if 'error' in message_lower or 'err' in message_lower:
            return 'ERROR'
        elif 'warn' in message_lower:
            return 'WARNING'
        elif 'info' in message_lower:
            return 'INFO'
        elif 'debug' in message_lower:
            return 'DEBUG'
        return 'UNKNOWN'
    
    async def create_healing_rule(self, anomaly: AnomalyResult):
        """Create or update infrastructure healing rule based on anomaly"""
        try:
            rule_name = f"auto-heal-{anomaly.metric_name.replace('_', '-')}"
            namespace = 'default'  # Should be configurable
            
            # Define healing rule based on anomaly type
            healing_rule = {
                'apiVersion': 'mlops.ai/v1',
                'kind': 'InfraHealingRule',
                'metadata': {
                    'name': rule_name,
                    'namespace': namespace,
                    'labels': {
                        'created-by': 'ai-engine',
                        'anomaly-type': anomaly.severity
                    }
                },
                'spec': {
                    'enabled': True,
                    'scope': {
                        'namespaces': [namespace],
                        'labels': anomaly.context.get('labels', {})
                    },
                    'scaling': {
                        'pods': {
                            'enabled': True,
                            'maxReplicas': 50,
                            'scaleUpThreshold': '70%',
                            'scaleDownThreshold': '30%'
                        }
                    },
                    'safeguards': {
                        'dryRun': True,  # Start with dry-run
                        'maxActionsPerHour': 5
                    }
                }
            }
            
            # Create or update the healing rule
            await self.custom_api.create_namespaced_custom_object(
                group='mlops.ai',
                version='v1',
                namespace=namespace,
                plural='infrahealingrules',
                body=healing_rule
            )
            
            logger.info(f"Created healing rule for anomaly: {rule_name}")
            
        except ApiException as e:
            if e.status == 409:  # Already exists, update it
                try:
                    await self.custom_api.patch_namespaced_custom_object(
                        group='mlops.ai',
                        version='v1',
                        namespace=namespace,
                        plural='infrahealingrules',
                        name=rule_name,
                        body=healing_rule
                    )
                except Exception as update_e:
                    logger.error(f"Failed to update healing rule: {update_e}")
            else:
                logger.error(f"Failed to create healing rule: {e}")
    
    async def create_autofix_policy(self, log_result: LogAnalysisResult):
        """Create autofix policy for code-level issues"""
        try:
            policy_name = f"autofix-{log_result.error_category.lower()}"
            namespace = 'default'
            
            autofix_policy = {
                'apiVersion': 'mlops.ai/v1',
                'kind': 'AutoFixPolicy',
                'metadata': {
                    'name': policy_name,
                    'namespace': namespace,
                    'labels': {
                        'created-by': 'ai-engine',
                        'error-category': log_result.error_category
                    }
                },
                'spec': {
                    'enabled': True,
                    'repositories': [{
                        'url': 'https://github.com/example/app',  # Should be detected
                        'allowedPaths': ['src/', 'config/'],
                        'excludedPaths': ['src/secrets/']
                    }],
                    'autoMerge': {
                        'enabled': False,  # Start conservative
                        'maxRiskLevel': 'low'
                    },
                    'riskAssessment': {
                        'dryRunFirst': True,
                        'maxChangesPerPR': 3
                    }
                }
            }
            
            await self.custom_api.create_namespaced_custom_object(
                group='mlops.ai',
                version='v1',
                namespace=namespace,
                plural='autofixpolicies',
                body=autofix_policy
            )
            
            logger.info(f"Created autofix policy for error: {policy_name}")
            
        except ApiException as e:
            if e.status != 409:  # Ignore if already exists
                logger.error(f"Failed to create autofix policy: {e}")
    
    async def run_analysis_cycle(self):
        """Run a complete analysis cycle"""
        logger.info("Starting analysis cycle")
        
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=5)
        
        try:
            # Fetch metrics data
            cpu_metrics = await self.fetch_metrics(
                'rate(container_cpu_usage_seconds_total[5m])', 
                start_time, end_time
            )
            memory_metrics = await self.fetch_metrics(
                'container_memory_usage_bytes', 
                start_time, end_time
            )
            
            # Fetch logs data
            error_logs = await self.fetch_logs(
                '{level="error"}', 
                start_time, end_time
            )
            
            # Analyze data
            cpu_anomalies = self.analyze_anomalies(cpu_metrics)
            memory_anomalies = self.analyze_anomalies(memory_metrics)
            log_issues = self.analyze_logs(error_logs)
            
            # Process results
            for anomaly in cpu_anomalies + memory_anomalies:
                if anomaly.severity in ['high', 'critical']:
                    await self.create_healing_rule(anomaly)
                    logger.warning(f"High-severity anomaly detected: {anomaly}")
            
            for issue in log_issues:
                if issue.confidence > 0.7:
                    await self.create_autofix_policy(issue)
                    logger.warning(f"Log issue detected: {issue}")
            
            logger.info(f"Analysis complete: {len(cpu_anomalies + memory_anomalies)} anomalies, {len(log_issues)} log issues")
            
        except Exception as e:
            logger.error(f"Analysis cycle failed: {e}")
    
    async def run(self):
        """Main run loop"""
        logger.info("Starting AI Analysis Engine")
        
        # Start metrics server
        start_http_server(8080)
        
        while True:
            try:
                await self.run_analysis_cycle()
                await asyncio.sleep(self.analysis_interval)
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                await asyncio.sleep(10)

def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    engine = AIAnalysisEngine()
    asyncio.run(engine.run())

if __name__ == '__main__':
    main()