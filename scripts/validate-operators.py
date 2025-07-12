#!/usr/bin/env python3
"""
MLOps Agent Stack - Operator Validation Script
This script validates that all operators are functioning correctly
"""

import asyncio
import aiohttp
import json
import sys
import time
from typing import Dict, List, Optional
import argparse


class OperatorValidator:
    """Validates MLOps operators functionality"""
    
    def __init__(self, namespace: str = "mlops-agent-stack", timeout: int = 30):
        self.namespace = namespace
        self.timeout = timeout
        self.base_ports = {
            "ai-engine": 8080,
            "infrastructure-healer": 8081, 
            "code-autofix": 8082
        }
        
    async def check_health_endpoint(self, component: str, port: int) -> Dict:
        """Check health endpoint of a component"""
        url = f"http://localhost:{port}/health"
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "component": component,
                            "status": "healthy",
                            "response_time": response.headers.get("response-time", "unknown"),
                            "data": data
                        }
                    else:
                        return {
                            "component": component,
                            "status": "unhealthy",
                            "error": f"HTTP {response.status}",
                            "data": None
                        }
        except Exception as e:
            return {
                "component": component,
                "status": "error",
                "error": str(e),
                "data": None
            }
    
    async def check_metrics_endpoint(self, component: str, port: int) -> Dict:
        """Check metrics endpoint of a component"""
        url = f"http://localhost:{port}/metrics"
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        text = await response.text()
                        # Count number of metrics
                        metrics_count = len([line for line in text.split('\n') if line and not line.startswith('#')])
                        return {
                            "component": component,
                            "status": "ok",
                            "metrics_count": metrics_count,
                            "has_custom_metrics": "mlops_" in text
                        }
                    else:
                        return {
                            "component": component,
                            "status": "error",
                            "error": f"HTTP {response.status}"
                        }
        except Exception as e:
            return {
                "component": component,
                "status": "error", 
                "error": str(e)
            }
    
    async def test_ai_engine_processing(self, port: int) -> Dict:
        """Test AI engine processing endpoint"""
        url = f"http://localhost:{port}/api/v1/analyze"
        test_data = {
            "metrics": {
                "timestamp": int(time.time()),
                "cpu_usage": 75.5,
                "memory_usage": 60.2,
                "pod_restarts": 0
            }
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(url, json=test_data) as response:
                    if response.status in [200, 202]:
                        data = await response.json()
                        return {
                            "test": "ai_processing",
                            "status": "pass",
                            "response": data
                        }
                    else:
                        return {
                            "test": "ai_processing",
                            "status": "fail",
                            "error": f"HTTP {response.status}"
                        }
        except Exception as e:
            return {
                "test": "ai_processing",
                "status": "error",
                "error": str(e)
            }
    
    async def test_healer_status(self, port: int) -> Dict:
        """Test infrastructure healer status endpoint"""
        url = f"http://localhost:{port}/api/v1/status"
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "test": "healer_status",
                            "status": "pass",
                            "active_observations": data.get("active_observations", 0),
                            "actions_taken": data.get("actions_taken", 0)
                        }
                    else:
                        return {
                            "test": "healer_status",
                            "status": "fail",
                            "error": f"HTTP {response.status}"
                        }
        except Exception as e:
            return {
                "test": "healer_status",
                "status": "error",
                "error": str(e)
            }
    
    async def validate_all_operators(self) -> Dict:
        """Run comprehensive validation of all operators"""
        results = {
            "validation_timestamp": int(time.time()),
            "namespace": self.namespace,
            "health_checks": [],
            "metrics_checks": [],
            "functional_tests": [],
            "summary": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0
            }
        }
        
        print("🔍 Starting operator validation...")
        print(f"Namespace: {self.namespace}")
        print(f"Timeout: {self.timeout}s")
        print()
        
        # Health checks
        print("1. Running health checks...")
        for component, port in self.base_ports.items():
            health_result = await self.check_health_endpoint(component, port)
            results["health_checks"].append(health_result)
            
            status_icon = "✅" if health_result["status"] == "healthy" else "❌"
            print(f"   {status_icon} {component}: {health_result['status']}")
            
            if health_result["status"] == "healthy":
                results["summary"]["passed"] += 1
            elif health_result["status"] == "error":
                results["summary"]["errors"] += 1
            else:
                results["summary"]["failed"] += 1
            results["summary"]["total_tests"] += 1
        
        print()
        
        # Metrics checks
        print("2. Running metrics checks...")
        for component, port in self.base_ports.items():
            metrics_result = await self.check_metrics_endpoint(component, port)
            results["metrics_checks"].append(metrics_result)
            
            status_icon = "✅" if metrics_result["status"] == "ok" else "❌"
            metrics_count = metrics_result.get("metrics_count", 0)
            print(f"   {status_icon} {component}: {metrics_count} metrics available")
            
            if metrics_result["status"] == "ok":
                results["summary"]["passed"] += 1
            elif metrics_result["status"] == "error":
                results["summary"]["errors"] += 1
            else:
                results["summary"]["failed"] += 1
            results["summary"]["total_tests"] += 1
        
        print()
        
        # Functional tests
        print("3. Running functional tests...")
        
        # Test AI Engine processing
        ai_test = await self.test_ai_engine_processing(self.base_ports["ai-engine"])
        results["functional_tests"].append(ai_test)
        status_icon = "✅" if ai_test["status"] == "pass" else "❌"
        print(f"   {status_icon} AI Engine processing: {ai_test['status']}")
        
        if ai_test["status"] == "pass":
            results["summary"]["passed"] += 1
        elif ai_test["status"] == "error":
            results["summary"]["errors"] += 1
        else:
            results["summary"]["failed"] += 1
        results["summary"]["total_tests"] += 1
        
        # Test Infrastructure Healer status
        healer_test = await self.test_healer_status(self.base_ports["infrastructure-healer"])
        results["functional_tests"].append(healer_test)
        status_icon = "✅" if healer_test["status"] == "pass" else "❌"
        print(f"   {status_icon} Infrastructure Healer status: {healer_test['status']}")
        
        if healer_test["status"] == "pass":
            results["summary"]["passed"] += 1
        elif healer_test["status"] == "error":
            results["summary"]["errors"] += 1
        else:
            results["summary"]["failed"] += 1
        results["summary"]["total_tests"] += 1
        
        print()
        
        # Summary
        total = results["summary"]["total_tests"]
        passed = results["summary"]["passed"]
        failed = results["summary"]["failed"]
        errors = results["summary"]["errors"]
        
        print("📊 Validation Summary:")
        print(f"   Total tests: {total}")
        print(f"   ✅ Passed: {passed}")
        print(f"   ❌ Failed: {failed}")
        print(f"   ⚠️  Errors: {errors}")
        
        success_rate = (passed / total * 100) if total > 0 else 0
        print(f"   📈 Success rate: {success_rate:.1f}%")
        
        print()
        
        if failed == 0 and errors == 0:
            print("🎉 All operator validations passed! Your MLOps operators are functioning correctly.")
            return_code = 0
        else:
            print("❌ Some validations failed. Please check the detailed results above.")
            return_code = 1
        
        return results, return_code


async def main():
    parser = argparse.ArgumentParser(description="Validate MLOps Agent Stack operators")
    parser.add_argument("--namespace", default="mlops-agent-stack", help="Kubernetes namespace")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds")
    parser.add_argument("--output", help="Output results to JSON file")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    validator = OperatorValidator(namespace=args.namespace, timeout=args.timeout)
    
    try:
        results, return_code = await validator.validate_all_operators()
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"📄 Detailed results saved to: {args.output}")
        
        if args.verbose:
            print("\n📋 Detailed Results:")
            print(json.dumps(results, indent=2))
        
        sys.exit(return_code)
        
    except KeyboardInterrupt:
        print("\n⏹️  Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Validation failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())