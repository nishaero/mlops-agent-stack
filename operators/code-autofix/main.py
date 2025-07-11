#!/usr/bin/env python3
"""
Code Autofix Operator for MLOps Agent Stack

This component handles:
- Linking log errors to source code locations
- Generating code fixes using fine-tuned LLM models
- Creating GitHub/GitLab pull requests with fixes
- Managing automated testing and code review workflows
"""

import asyncio
import logging
import os
import json
import subprocess
import tempfile
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import git
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from prometheus_client import start_http_server, Counter, Histogram, Gauge

# Metrics
FIXES_GENERATED = Counter('mlops_fixes_generated_total', 'Total code fixes generated', ['language', 'error_type'])
FIX_DURATION = Histogram('mlops_fix_generation_duration_seconds', 'Time spent generating fixes')
ACTIVE_POLICIES = Gauge('mlops_active_autofix_policies', 'Number of active autofix policies')
PRS_CREATED = Counter('mlops_pull_requests_created_total', 'Total pull requests created', ['repository', 'status'])

logger = logging.getLogger(__name__)

@dataclass
class CodeIssue:
    """Represents a code issue that needs fixing"""
    error_message: str
    file_path: str
    line_number: int
    error_type: str
    severity: str
    context: Dict[str, Any]
    suggested_fix: Optional[str] = None
    confidence: float = 0.0

@dataclass
class FixResult:
    """Result of a code fix operation"""
    original_code: str
    fixed_code: str
    explanation: str
    test_code: str
    confidence: float
    risk_level: str  # low, medium, high

class GitHubClient:
    """GitHub API client for repository operations"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    async def create_fork(self, owner: str, repo: str) -> Dict:
        """Create a fork of the repository"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/repos/{owner}/{repo}/forks"
            async with session.post(url, headers=self.headers) as response:
                if response.status == 202:
                    return await response.json()
                else:
                    raise Exception(f"Failed to create fork: {response.status}")
    
    async def create_branch(self, owner: str, repo: str, branch_name: str, base_sha: str) -> Dict:
        """Create a new branch"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/repos/{owner}/{repo}/git/refs"
            data = {
                "ref": f"refs/heads/{branch_name}",
                "sha": base_sha
            }
            async with session.post(url, headers=self.headers, json=data) as response:
                if response.status == 201:
                    return await response.json()
                else:
                    raise Exception(f"Failed to create branch: {response.status}")
    
    async def update_file(self, owner: str, repo: str, path: str, content: str, 
                         message: str, branch: str, sha: Optional[str] = None) -> Dict:
        """Update or create a file in the repository"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
            data = {
                "message": message,
                "content": content,
                "branch": branch
            }
            if sha:
                data["sha"] = sha
            
            method = session.put if sha else session.put
            async with method(url, headers=self.headers, json=data) as response:
                if response.status in [200, 201]:
                    return await response.json()
                else:
                    raise Exception(f"Failed to update file: {response.status}")
    
    async def create_pull_request(self, owner: str, repo: str, title: str, 
                                 body: str, head: str, base: str = "main") -> Dict:
        """Create a pull request"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
            data = {
                "title": title,
                "body": body,
                "head": head,
                "base": base
            }
            async with session.post(url, headers=self.headers, json=data) as response:
                if response.status == 201:
                    return await response.json()
                else:
                    raise Exception(f"Failed to create PR: {response.status}")

class CodeLLMClient:
    """Client for Code LLM inference"""
    
    def __init__(self, model_endpoint: str = "http://codellama-service:8080"):
        self.model_endpoint = model_endpoint
    
    async def generate_fix(self, error_message: str, code_context: str, 
                          file_path: str, line_number: int) -> FixResult:
        """Generate a code fix using the LLM"""
        
        # Construct prompt for code fixing
        prompt = f"""
Fix the following code error:

Error: {error_message}
File: {file_path}
Line: {line_number}

Code context:
```
{code_context}
```

Please provide:
1. The corrected code
2. A brief explanation of the fix
3. A unit test to verify the fix
4. Risk assessment (low/medium/high)

Response format (JSON):
{{
    "fixed_code": "...",
    "explanation": "...",
    "test_code": "...",
    "risk_level": "low|medium|high",
    "confidence": 0.95
}}
"""
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "prompt": prompt,
                    "max_tokens": 2048,
                    "temperature": 0.1,
                    "stop": ["```"]
                }
                
                async with session.post(f"{self.model_endpoint}/generate", 
                                      json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        generated_text = result.get("text", "")
                        
                        # Parse the JSON response from the model
                        try:
                            fix_data = json.loads(generated_text)
                            return FixResult(
                                original_code=code_context,
                                fixed_code=fix_data.get("fixed_code", ""),
                                explanation=fix_data.get("explanation", ""),
                                test_code=fix_data.get("test_code", ""),
                                confidence=fix_data.get("confidence", 0.5),
                                risk_level=fix_data.get("risk_level", "medium")
                            )
                        except json.JSONDecodeError:
                            # Fallback to simple text parsing
                            return self.parse_text_response(generated_text, code_context)
                    else:
                        logger.error(f"LLM API error: {response.status}")
                        return self.create_fallback_fix(error_message, code_context)
                        
        except Exception as e:
            logger.error(f"Failed to generate fix: {e}")
            return self.create_fallback_fix(error_message, code_context)
    
    def parse_text_response(self, text: str, original_code: str) -> FixResult:
        """Parse LLM text response as fallback"""
        # Simple parsing logic for non-JSON responses
        return FixResult(
            original_code=original_code,
            fixed_code=text[:500],  # Truncate for safety
            explanation="Automatic fix generated",
            test_code="# TODO: Add test",
            confidence=0.3,
            risk_level="high"
        )
    
    def create_fallback_fix(self, error_message: str, code_context: str) -> FixResult:
        """Create a simple fallback fix"""
        if "null pointer" in error_message.lower() or "nullpointerexception" in error_message.lower():
            fixed_code = code_context.replace("object.", "if (object != null) object.")
            explanation = "Added null check to prevent NullPointerException"
            risk_level = "low"
        else:
            fixed_code = f"// TODO: Fix error: {error_message}\n{code_context}"
            explanation = "Added TODO comment for manual review"
            risk_level = "high"
        
        return FixResult(
            original_code=code_context,
            fixed_code=fixed_code,
            explanation=explanation,
            test_code="# TODO: Add appropriate test",
            confidence=0.1,
            risk_level=risk_level
        )

class CodeAutofixOperator:
    """Main Code Autofix Operator"""
    
    def __init__(self):
        self.github_token = self.get_secret_value('github-token', 'token')
        self.gitlab_token = self.get_secret_value('gitlab-token', 'token')
        self.reconcile_interval = int(os.getenv('RECONCILE_INTERVAL', '60'))
        
        # Initialize clients
        self.github_client = GitHubClient(self.github_token) if self.github_token else None
        self.llm_client = CodeLLMClient()
        
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        
        self.k8s_client = client.ApiClient()
        self.core_v1 = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()
        
        # Processing state
        self.active_fixes = {}
        self.fix_history = []
    
    def get_secret_value(self, secret_name: str, key: str) -> Optional[str]:
        """Get value from Kubernetes secret"""
        try:
            secret = self.core_v1.read_namespaced_secret(
                name=secret_name,
                namespace=os.getenv('NAMESPACE', 'default')
            )
            return secret.data.get(key, b'').decode('utf-8')
        except Exception as e:
            logger.warning(f"Failed to get secret {secret_name}/{key}: {e}")
            return None
    
    async def get_autofix_policies(self) -> List[Dict]:
        """Get all AutoFixPolicy resources"""
        try:
            policies = await self.custom_api.list_cluster_custom_object(
                group='mlops.ai',
                version='v1',
                plural='autofixpolicies'
            )
            return policies.get('items', [])
        except ApiException as e:
            if e.status != 404:
                logger.error(f"Failed to get autofix policies: {e}")
            return []
    
    async def detect_code_issues_from_logs(self) -> List[CodeIssue]:
        """Detect code issues from application logs"""
        issues = []
        
        # Get recent error logs that might indicate code issues
        try:
            pods = await self.core_v1.list_pod_for_all_namespaces()
            
            for pod in pods.items:
                if pod.status.phase != 'Running':
                    continue
                
                # Check pod logs for errors
                try:
                    logs = await self.core_v1.read_namespaced_pod_log(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        tail_lines=100
                    )
                    
                    # Parse logs for code-related errors
                    parsed_issues = self.parse_logs_for_issues(logs, pod.metadata.labels)
                    issues.extend(parsed_issues)
                    
                except Exception as e:
                    logger.debug(f"Could not read logs for pod {pod.metadata.name}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to detect code issues from logs: {e}")
        
        return issues
    
    def parse_logs_for_issues(self, logs: str, pod_labels: Dict[str, str]) -> List[CodeIssue]:
        """Parse log text to extract code issues"""
        issues = []
        lines = logs.split('\n')
        
        for i, line in enumerate(lines):
            # Look for common error patterns
            if any(pattern in line.lower() for pattern in [
                'nullpointerexception', 'arrayindexoutofbounds', 'classnotfound',
                'illegalargument', 'nosuchelement', 'classcast', 'arithmetic'
            ]):
                # Extract file and line information from stack traces
                file_path, line_number = self.extract_location_from_stacktrace(lines[i:i+10])
                
                if file_path:
                    issue = CodeIssue(
                        error_message=line.strip(),
                        file_path=file_path,
                        line_number=line_number,
                        error_type=self.classify_error_type(line),
                        severity=self.assess_error_severity(line),
                        context={
                            'pod_labels': pod_labels,
                            'log_context': lines[max(0, i-2):i+3],
                            'timestamp': datetime.now().isoformat()
                        }
                    )
                    issues.append(issue)
        
        return issues
    
    def extract_location_from_stacktrace(self, lines: List[str]) -> tuple:
        """Extract file path and line number from stack trace"""
        for line in lines:
            # Look for Java stack trace pattern
            if 'at ' in line and '.java:' in line:
                parts = line.split('(')
                if len(parts) > 1:
                    location = parts[1].replace(')', '')
                    if ':' in location:
                        file_part, line_part = location.split(':')
                        try:
                            return file_part, int(line_part)
                        except ValueError:
                            pass
            
            # Look for Python stack trace pattern
            if 'File "' in line and ', line ' in line:
                try:
                    file_start = line.index('File "') + 6
                    file_end = line.index('", line')
                    line_start = line.index(', line ') + 7
                    line_end = line.index(',', line_start) if ',' in line[line_start:] else len(line)
                    
                    file_path = line[file_start:file_end]
                    line_number = int(line[line_start:line_end])
                    return file_path, line_number
                except (ValueError, IndexError):
                    pass
        
        return None, 0
    
    def classify_error_type(self, error_line: str) -> str:
        """Classify the type of error"""
        error_lower = error_line.lower()
        
        if 'nullpointer' in error_lower:
            return 'NullPointerException'
        elif 'arrayindex' in error_lower:
            return 'ArrayIndexOutOfBoundsException'
        elif 'classnotfound' in error_lower:
            return 'ClassNotFoundException'
        elif 'illegalargument' in error_lower:
            return 'IllegalArgumentException'
        elif 'arithmetic' in error_lower:
            return 'ArithmeticException'
        else:
            return 'UnknownError'
    
    def assess_error_severity(self, error_line: str) -> str:
        """Assess the severity of an error"""
        error_lower = error_line.lower()
        
        if any(critical in error_lower for critical in ['fatal', 'critical', 'severe']):
            return 'critical'
        elif any(high in error_lower for high in ['error', 'exception', 'failed']):
            return 'high'
        elif any(medium in error_lower for medium in ['warning', 'warn']):
            return 'medium'
        else:
            return 'low'
    
    async def generate_fix_for_issue(self, issue: CodeIssue, repository_config: Dict) -> Optional[FixResult]:
        """Generate a fix for a specific code issue"""
        try:
            # Clone repository to get code context
            repo_url = repository_config['url']
            branch = repository_config.get('branch', 'main')
            
            with tempfile.TemporaryDirectory() as temp_dir:
                # Clone repository
                repo = git.Repo.clone_from(repo_url, temp_dir, branch=branch)
                
                # Read the problematic file
                file_full_path = Path(temp_dir) / issue.file_path
                if not file_full_path.exists():
                    logger.warning(f"File not found: {issue.file_path}")
                    return None
                
                with open(file_full_path, 'r') as f:
                    lines = f.readlines()
                
                # Get context around the error line
                start_line = max(0, issue.line_number - 10)
                end_line = min(len(lines), issue.line_number + 10)
                code_context = ''.join(lines[start_line:end_line])
                
                # Generate fix using LLM
                with FIX_DURATION.time():
                    fix_result = await self.llm_client.generate_fix(
                        issue.error_message,
                        code_context,
                        issue.file_path,
                        issue.line_number
                    )
                
                FIXES_GENERATED.labels(
                    language=self.detect_language(issue.file_path),
                    error_type=issue.error_type
                ).inc()
                
                return fix_result
                
        except Exception as e:
            logger.error(f"Failed to generate fix for issue {issue.file_path}:{issue.line_number}: {e}")
            return None
    
    def detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension"""
        ext = Path(file_path).suffix.lower()
        language_map = {
            '.py': 'python',
            '.java': 'java',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.go': 'go',
            '.rs': 'rust',
            '.cpp': 'cpp',
            '.c': 'c'
        }
        return language_map.get(ext, 'unknown')
    
    async def create_pull_request_with_fix(self, issue: CodeIssue, fix_result: FixResult, 
                                          repository_config: Dict, policy: Dict) -> bool:
        """Create a pull request with the generated fix"""
        try:
            repo_url = repository_config['url']
            # Parse GitHub URL (simplified)
            if 'github.com' not in repo_url:
                logger.error("Only GitHub repositories are supported currently")
                return False
            
            # Extract owner and repo name
            url_parts = repo_url.replace('https://github.com/', '').replace('.git', '').split('/')
            if len(url_parts) != 2:
                logger.error(f"Invalid GitHub URL format: {repo_url}")
                return False
            
            owner, repo_name = url_parts
            
            # Create branch name
            branch_name = f"autofix/{issue.error_type.lower()}/{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            
            # Create fork (if needed) and branch
            base_branch = repository_config.get('branch', 'main')
            
            # Get base SHA
            # This is simplified - in production you'd get the actual SHA
            base_sha = "main"  # Placeholder
            
            if self.github_client:
                # Create branch
                await self.github_client.create_branch(owner, repo_name, branch_name, base_sha)
                
                # Update file with fix
                import base64
                content_b64 = base64.b64encode(fix_result.fixed_code.encode()).decode()
                
                await self.github_client.update_file(
                    owner, repo_name, issue.file_path, content_b64,
                    f"Fix {issue.error_type} in {issue.file_path}",
                    branch_name
                )
                
                # Create PR
                pr_title = f"🤖 Autofix: {issue.error_type} in {issue.file_path}"
                pr_body = f"""
## Automated Code Fix

**Error:** {issue.error_message}
**File:** {issue.file_path}:{issue.line_number}
**Fix Confidence:** {fix_result.confidence:.2%}
**Risk Level:** {fix_result.risk_level}

### Explanation
{fix_result.explanation}

### Changes
- Fixed {issue.error_type} in {issue.file_path}
- Added null checks and error handling
- Risk assessment: {fix_result.risk_level}

### Testing
```
{fix_result.test_code}
```

---
*This PR was automatically generated by MLOps Agent Stack*
*Please review carefully before merging*
"""
                
                pr_result = await self.github_client.create_pull_request(
                    owner, repo_name, pr_title, pr_body, branch_name, base_branch
                )
                
                PRS_CREATED.labels(repository=repo_name, status='created').inc()
                logger.info(f"Created PR #{pr_result['number']} for {issue.file_path}")
                
                return True
            
        except Exception as e:
            logger.error(f"Failed to create PR for fix: {e}")
            PRS_CREATED.labels(repository=repository_config.get('url', 'unknown'), status='failed').inc()
            return False
    
    async def process_autofix_policies(self):
        """Process all autofix policies and generate fixes"""
        policies = await self.get_autofix_policies()
        ACTIVE_POLICIES.set(len(policies))
        
        # Detect issues from logs
        detected_issues = await self.detect_code_issues_from_logs()
        
        for policy in policies:
            try:
                if not policy.get('spec', {}).get('enabled', True):
                    continue
                
                # Process each repository in the policy
                repositories = policy.get('spec', {}).get('repositories', [])
                
                for repo_config in repositories:
                    # Filter issues that match allowed paths
                    allowed_paths = repo_config.get('allowedPaths', [])
                    excluded_paths = repo_config.get('excludedPaths', [])
                    
                    filtered_issues = self.filter_issues_by_paths(
                        detected_issues, allowed_paths, excluded_paths
                    )
                    
                    # Generate fixes for high-confidence issues
                    for issue in filtered_issues[:5]:  # Limit concurrent fixes
                        if issue.severity in ['high', 'critical']:
                            fix_result = await self.generate_fix_for_issue(issue, repo_config)
                            
                            if fix_result and fix_result.confidence > 0.7:
                                # Check risk assessment
                                risk_assessment = policy.get('spec', {}).get('riskAssessment', {})
                                if self.should_create_pr(fix_result, risk_assessment):
                                    await self.create_pull_request_with_fix(
                                        issue, fix_result, repo_config, policy
                                    )
                
            except Exception as e:
                logger.error(f"Failed to process policy {policy.get('metadata', {}).get('name', 'unknown')}: {e}")
    
    def filter_issues_by_paths(self, issues: List[CodeIssue], 
                              allowed_paths: List[str], excluded_paths: List[str]) -> List[CodeIssue]:
        """Filter issues based on allowed/excluded paths"""
        filtered = []
        
        for issue in issues:
            # Check if file matches allowed paths
            if allowed_paths:
                if not any(issue.file_path.startswith(path) for path in allowed_paths):
                    continue
            
            # Check if file matches excluded paths
            if excluded_paths:
                if any(issue.file_path.startswith(path) for path in excluded_paths):
                    continue
            
            filtered.append(issue)
        
        return filtered
    
    def should_create_pr(self, fix_result: FixResult, risk_assessment: Dict) -> bool:
        """Determine if PR should be created based on risk assessment"""
        if risk_assessment.get('dryRunFirst', True) and fix_result.risk_level == 'high':
            return False
        
        max_risk = risk_assessment.get('maxRiskLevel', 'medium')
        risk_levels = {'low': 1, 'medium': 2, 'high': 3}
        
        return risk_levels.get(fix_result.risk_level, 3) <= risk_levels.get(max_risk, 2)
    
    async def run(self):
        """Main run loop"""
        logger.info("Starting Code Autofix Operator")
        
        # Start metrics server
        start_http_server(8080)
        
        while True:
            try:
                await self.process_autofix_policies()
                await asyncio.sleep(self.reconcile_interval)
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                await asyncio.sleep(10)

def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    operator = CodeAutofixOperator()
    asyncio.run(operator.run())

if __name__ == '__main__':
    main()