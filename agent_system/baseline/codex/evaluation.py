#!/usr/bin/env python3
"""
Codex evaluation module that follows DevEval's evaluation patterns.
However, the evaluation is based on resolved/total experiments, not averaged by code lines as mentioned in the paper.
This mirrors the Test class behavior from DevEval's test.py.
"""

import json
import logging
import os
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class CodexEvaluator:
    """Evaluator for Codex-generated code following DevEval patterns."""
    
    def __init__(self, workspace_path: Path, repo_path: Path, language: str = "python"):
        """Initialize evaluator with workspace and repository paths."""
        self.workspace_path = Path(workspace_path)
        self.repo_path = Path(repo_path)
        self.language = language
        
        # Load repo config to get test and dependency paths
        repo_config_path = repo_path / "repo_config.json"
        if repo_config_path.exists():
            with open(repo_config_path, 'r') as f:
                self.repo_config = json.load(f)
        else:
            logger.warning(f"repo_config.json not found at {repo_config_path}")
            self.repo_config = {}
        
        # Extract configuration
        self.dependencies = self.repo_config.get("dependencies", "")
        self.setup_shell_script = self.repo_config.get("setup_shell_script", "")
        self.unit_tests_path = self.repo_config.get("unit_tests", "unit_tests")
        self.acceptance_tests_path = self.repo_config.get("acceptance_tests", "acceptance_tests")
        self.unit_tests_command = self.repo_config.get("unit_test_script", "")
        self.acceptance_tests_command = self.repo_config.get("acceptance_test_script", "")
        
        logger.info(f"Evaluator initialized for {language} project")
        logger.info(f"Workspace: {self.workspace_path}")
        logger.info(f"Repository: {self.repo_path}")
    
    def evaluate(self, phase: str) -> Dict[str, Any]:
        """Evaluate the generated code for the given phase."""
        logger.info(f"Starting evaluation for {phase} phase")
        
        try:
            if phase == "Implementation":
                return self._evaluate_implementation()
            elif phase == "UnitTesting":
                return self._evaluate_unit_testing()
            elif phase == "AcceptanceTesting":
                return self._evaluate_acceptance_testing()
            else:
                raise ValueError(f"Unknown phase: {phase}")
        
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return {
                "success": False,
                "phase": phase,
                "error": str(e),
                "details": {}
            }
    
    def _evaluate_implementation(self) -> Dict[str, Any]:
        """Evaluate Implementation phase by running unit and acceptance tests."""
        logger.info("Evaluating Implementation phase")
        
        # Setup test environment
        self._setup_test_environment()
        
        # Run unit tests
        unit_result = self._run_tests("unit_tests")
        logger.info(f"Unit tests result: {'PASS' if unit_result['success'] else 'FAIL'}")
        
        # Run acceptance tests
        acceptance_result = self._run_tests("acceptance_tests")
        logger.info(f"Acceptance tests result: {'PASS' if acceptance_result['success'] else 'FAIL'}")
        
        # Overall success if both pass
        overall_success = unit_result['success'] and acceptance_result['success']
        
        return {
            "success": overall_success,
            "phase": "Implementation",
            "unit_tests": unit_result,
            "acceptance_tests": acceptance_result,
            "details": {
                "unit_output": unit_result.get("output", ""),
                "acceptance_output": acceptance_result.get("output", ""),
                "workspace_path": str(self.workspace_path)
            }
        }
    
    def _evaluate_unit_testing(self) -> Dict[str, Any]:
        """Evaluate UnitTesting phase by running generated unit tests on reference implementation."""
        logger.info("Evaluating UnitTesting phase")
        
        # Setup test environment
        self._setup_test_environment()
        
        # Run the generated unit tests
        result = self._run_tests("unit_tests")
        
        return {
            "success": result['success'],
            "phase": "UnitTesting",
            "test_result": result,
            "details": {
                "output": result.get("output", ""),
                "workspace_path": str(self.workspace_path)
            }
        }
    
    def _evaluate_acceptance_testing(self) -> Dict[str, Any]:
        """Evaluate AcceptanceTesting phase by running generated acceptance tests on reference implementation."""
        logger.info("Evaluating AcceptanceTesting phase")
        
        # Setup test environment
        self._setup_test_environment()
        
        # Run the generated acceptance tests
        result = self._run_tests("acceptance_tests")
        
        return {
            "success": result['success'],
            "phase": "AcceptanceTesting",
            "test_result": result,
            "details": {
                "output": result.get("output", ""),
                "workspace_path": str(self.workspace_path)
            }
        }
    
    def _setup_test_environment(self):
        """Setup test environment by installing dependencies."""
        logger.info("Setting up test environment")
        
        if self.language == "python" and self.dependencies:
            # Use relative path like original DevEval, with workspace as working directory
            logger.info(f"Installing dependencies from {self.dependencies}")
            try:
                result = subprocess.run(
                    ["pip", "install", "-r", self.dependencies],
                    cwd=self.workspace_path,  # Set working directory to workspace
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if result.returncode == 0:
                    logger.info("Dependencies installed successfully")
                else:
                    logger.warning(f"Dependencies installation failed: {result.stderr}")
            
            except subprocess.TimeoutExpired:
                logger.warning("Dependencies installation timed out")
            except Exception as e:
                logger.warning(f"Dependencies installation error: {e}")
        
        # Run setup script if available
        if self.setup_shell_script:
            logger.info(f"Running setup script: {self.setup_shell_script}")
            try:
                result = subprocess.run(
                    ["sh", self.setup_shell_script],  # Use relative path
                    cwd=self.workspace_path,  # Set working directory to workspace
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode == 0:
                    logger.info("Setup script completed successfully")
                else:
                    logger.warning(f"Setup script failed: {result.stderr}")
            
            except Exception as e:
                logger.warning(f"Setup script error: {e}")
    
    def _run_tests(self, test_type: str) -> Dict[str, Any]:
        """Run tests and return results."""
        logger.info(f"Running {test_type}")
        
        if test_type == "unit_tests":
            test_path = self.unit_tests_path
            test_command = self.unit_tests_command
        elif test_type == "acceptance_tests":
            test_path = self.acceptance_tests_path
            test_command = self.acceptance_tests_command
        else:
            raise ValueError(f"Unknown test type: {test_type}")
        
        test_dir = self.workspace_path / test_path if test_path else self.workspace_path
        
        if not test_dir.exists():
            logger.warning(f"Test directory not found: {test_dir}")
            return {
                "success": False,
                "output": f"Test directory not found: {test_dir}",
                "error": "Test directory missing"
            }
        
        try:
            if self.language == "python":
                # Use pytest for Python projects
                cmd = ["pytest", "--cov=.", str(test_path)] if test_path else ["pytest", "--cov=."]
            else:
                # Use custom test command
                if not test_command:
                    logger.error(f"No test command specified for {test_type}")
                    return {
                        "success": False,
                        "output": f"No test command specified for {test_type}",
                        "error": "Missing test command"
                    }
                cmd = test_command.split() if isinstance(test_command, str) else test_command
            
            logger.info(f"Executing: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
            cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            output = result.stdout + result.stderr
            logger.debug(f"Test output: {output}")
            
            # Check for success patterns in output
            success = self._check_test_success(output, result.returncode)
            
            return {
                "success": success,
                "output": output,
                "returncode": result.returncode,
                "command": " ".join(cmd)
            }
                
        except subprocess.TimeoutExpired:
            logger.error(f"Test execution timed out for {test_type}")
            return {
                "success": False,
                "output": "Test execution timed out",
                "error": "Timeout"
            }
        except Exception as e:
            logger.error(f"Test execution failed for {test_type}: {e}")
            return {
                "success": False,
                "output": str(e),
                "error": str(e)
            }
    
    def _check_test_success(self, output: str, returncode: int) -> bool:
        """Check if tests passed based on output and return code."""
        # Primary indicator: return code 0
        if returncode == 0:
            return True
        
        # Secondary checks for common test failure patterns
        failure_patterns = [
            "FAILED",
            "ERROR",
            "FAIL",
            "failed",
            "error",
            "Error:",
            "Exception:",
            "Traceback"
        ]
        
        # If any failure pattern is found, it's likely a failure
        for pattern in failure_patterns:
            if pattern in output:
                return False
        
        # Success patterns
        success_patterns = [
            "ALL_PASSED",
            "all tests passed",
            "0 failed",
            "passed",
            "OK"
        ]
        
        for pattern in success_patterns:
            if pattern.lower() in output.lower():
                return True
        
        # Default to failure if uncertain
        return False


def main():
    """Test the evaluator."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Codex evaluator")
    parser.add_argument("--workspace", required=True, help="Workspace path")
    parser.add_argument("--repo", required=True, help="Repository path") 
    parser.add_argument("--phase", required=True, choices=["Implementation", "UnitTesting", "AcceptanceTesting"])
    parser.add_argument("--language", default="python", help="Programming language")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    evaluator = CodexEvaluator(
        workspace_path=Path(args.workspace),
        repo_path=Path(args.repo),
        language=args.language
    )
    
    result = evaluator.evaluate(args.phase)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main() 