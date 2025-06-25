#!/usr/bin/env python3
"""
DevEval Claude Code runner that uses adapted DevEval prompts and environment setup.

It supports the following phases:
- Implementation
- UnitTesting
- AcceptanceTesting
"""

import json
import os
import sys
import tempfile
import argparse
import logging
import subprocess
import shutil
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Add the current directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))
from prompt_builder import DevEvalPromptBuilder

# Setup logging - we'll configure handlers later
logger = logging.getLogger(__name__)


class ClaudeCodeExecutor:
    """Handles Claude Code CLI execution with proper environment setup."""
    
    def __init__(self, model: str = "claude-3-5-sonnet-20241022", livestream: bool = False):
        self.model = model
        self._verify_setup()
        self.livestream = livestream
    
    def _verify_setup(self):
        """Verify Claude Code CLI and environment setup."""
        try:
            result = subprocess.run(["claude", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"Using Claude Code CLI: {result.stdout.strip()}")
            else:
                logger.warning("Claude Code CLI version check failed")
        except FileNotFoundError:
            logger.error("Claude Code CLI not found. Please install Claude Code CLI first.")
            sys.exit(1)
    
    def run_claude_code(self, prompt: str, workspace_dir: Path) -> Dict[str, Any]:
        """Run Claude Code CLI with given prompt in workspace directory."""
        logger.info(f"Executing Claude Code with model {self.model}")
        logger.info(f"Workspace directory: {workspace_dir}")
        logger.info(f"Prompt length: {len(prompt)} characters")
        
        # Set Anthropic API key if available
        env = os.environ.copy()
        if "ANTHROPIC_API_KEY" not in env:
            logger.warning("ANTHROPIC_API_KEY not set in environment")
        
        # Set model environment variable
        env["ANTHROPIC_MODEL"] = self.model
        
        # Prepare Claude Code command with allowed tools (based on terminal-bench implementation)
        allowed_tools = [
            "Bash", "Edit", "Write", "Read", "Glob", "Grep", "LS", 
            "WebFetch", "NotebookEdit", "NotebookRead", "TodoRead", "TodoWrite", "Agent"
        ]
        
        cmd = [
            "claude",
            "-p", prompt,
            "--allowedTools"
        ] + allowed_tools
        
        logger.info(f"Executing command: {' '.join(cmd[:2])} [PROMPT] {' '.join(cmd[3:])}")
        logger.info("Starting Claude Code execution...")
        
        try:
            # Always use Popen for real-time output processing
            process = subprocess.Popen(
                cmd,
                cwd=workspace_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            
            logger.info(f"Claude Code process started with PID: {process.pid}")
            
            stdout_lines = []
            stderr_lines = []
            start_time = time.time()
            last_update_time = start_time
            
            # Process output in real-time regardless of livestream mode
            if self.livestream:
                logger.info("=== CLAUDE CODE LIVESTREAM OUTPUT ===")
            
            # Stream output in real-time
            while True:
                # Check if process has ended
                if process.poll() is not None:
                    break
                
                # Read stdout without blocking
                output = process.stdout.readline()
                if output:
                    stdout_lines.append(output)
                    logger.debug(f"CLAUDE CODE OUTPUT: {output.strip()}")  # Always log to file
                    
                    # Only print to terminal in livestream mode
                    if self.livestream:
                        print(output.strip())
                
                # Read stderr without blocking
                error = process.stderr.readline()
                if error:
                    stderr_lines.append(error)
                    logger.debug(f"CLAUDE CODE STDERR: {error.strip()}")  # Always log to file
                
                # Print periodic updates if not in livestream mode
                current_time = time.time()
                if not self.livestream and (current_time - last_update_time) >= 10:
                    elapsed = int(current_time - start_time)
                    logger.info(f"Claude Code still running... ({elapsed}s elapsed)")
                    last_update_time = current_time
                
                # Small sleep to prevent CPU hogging
                time.sleep(0.1)
            
            # Collect any remaining output
            remaining_stdout, remaining_stderr = process.communicate()
            if remaining_stdout:
                stdout_lines.append(remaining_stdout)
                logger.debug(f"CLAUDE CODE FINAL OUTPUT: {remaining_stdout.strip()}")
            if remaining_stderr:
                stderr_lines.append(remaining_stderr)
                logger.debug(f"CLAUDE CODE FINAL STDERR: {remaining_stderr.strip()}")
            
            stdout = ''.join(stdout_lines)
            stderr = ''.join(stderr_lines)
            returncode = process.returncode
            
            if self.livestream:
                logger.info("=== END CLAUDE CODE LIVESTREAM ===")
            
            logger.info("Claude Code process completed")
            logger.info(f"Claude Code execution finished with return code: {returncode}")
            logger.info(f"Stdout length: {len(stdout)} characters")
            logger.info(f"Stderr length: {len(stderr)} characters")
            
            if returncode == 0:
                return {
                    "success": True,
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": returncode
                }
            else:
                logger.error(f"Claude Code execution failed with return code {returncode}")
                logger.error(f"Stderr: {stderr}")
                return {
                    "success": False,
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": returncode,
                    "error": f"Claude Code failed with return code {returncode}"
                }
                
        except FileNotFoundError:
            error_msg = "Claude Code CLI not found. Please install Claude Code CLI first."
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "stdout": "",
                "stderr": "",
                "returncode": -1
            }
        except Exception as e:
            error_msg = f"Claude Code execution error: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "stdout": "",
                "stderr": "",
                "returncode": -1
            }


class DevEvalClaudeCodeRunner:
    """Main runner for DevEval with Claude Code integration."""
    
    def __init__(self, repo_path: Path, config_root: Path, executor: ClaudeCodeExecutor):
        self.repo_path = repo_path
        self.executor = executor
        self.prompt_builder = DevEvalPromptBuilder(repo_path, config_root)
        
        # Load repo config
        with open(repo_path / "repo_config.json", "r") as f:
            self.repo_config = json.load(f)
    
    def setup_workspace_for_implementation(self, workspace_dir: Path):
        """Setup workspace for Implementation phase like ChatDev does."""
        logger.info("Setting up workspace for Implementation phase")
        
        # Copy required files (dependencies, tests, etc.) like prepare_required_files
        required_files = self.repo_config.get("required_files", [])
        unit_tests = self.repo_config.get("unit_tests", "")
        acceptance_tests = self.repo_config.get("acceptance_tests", "")
        dependencies = self.repo_config.get("dependencies", "")
        setup_shell_script = self.repo_config.get("setup_shell_script", "")
        
        # Copy dependencies
        if dependencies:
            self._copy_file(dependencies, self.repo_path, workspace_dir)
        
        # Copy setup script
        if setup_shell_script:
            self._copy_file(setup_shell_script, self.repo_path, workspace_dir)
        
        # Copy test files
        if unit_tests:
            self._copy_file(unit_tests, self.repo_path, workspace_dir)
        if acceptance_tests:
            self._copy_file(acceptance_tests, self.repo_path, workspace_dir)
        
        # Copy required files
        for required_file in required_files:
            if '*' in required_file:
                # Handle wildcards by copying the directory
                self._copy_file(required_file.split('/*')[0], self.repo_path, workspace_dir)
            else:
                self._copy_file(required_file, self.repo_path, workspace_dir)
        
        logger.info("Implementation workspace setup completed")
    
    def setup_workspace_for_testing(self, workspace_dir: Path, phase: str):
        """Setup workspace for UnitTesting/AcceptanceTesting phases like ChatDev does."""
        logger.info(f"Setting up workspace for {phase} phase")
        
        # Copy entire source to workspace (like src2tgt does)
        shutil.copytree(self.repo_path, workspace_dir, dirs_exist_ok=True)
        
        # Remove the test files that agent needs to generate
        if phase == "UnitTesting":
            test_prompts = self.repo_config.get("fine_unit_test_prompt", {})
        else:  # AcceptanceTesting
            test_prompts = self.repo_config.get("fine_acceptance_test_prompt", {})
        
        for filename in test_prompts.keys():
            file_path = workspace_dir / filename
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Removed existing test file: {filename}")
        
        logger.info(f"{phase} workspace setup completed")
    
    def _copy_file(self, file_path: str, src_path: Path, tgt_path: Path):
        """Copy file from src to target, creating directories as needed."""
        if not file_path:
            return
        
        src_file = src_path / file_path
        tgt_file = tgt_path / file_path
        
        if not src_file.exists():
            logger.warning(f"Source file not found: {src_file}")
            return
        
        # Create target directory
        tgt_file.parent.mkdir(parents=True, exist_ok=True)
        
        if src_file.is_dir():
            shutil.copytree(src_file, tgt_file, dirs_exist_ok=True)
        else:
            shutil.copy2(src_file, tgt_file)
        
        logger.debug(f"Copied: {file_path}")
    
    def _parse_claude_code_response(self, raw_output: str) -> Dict[str, Any]:
        """Parse Claude Code raw output to extract and process content."""
        try:
            # Parse Claude Code JSON response format
            lines = [line.strip() for line in raw_output.split('\n') if line.strip()]
            
            parsed_response = {
                "claude_code_messages": [],
                "response_content": "",
                "function_calls": [],
                "error": None
            }
            
            for line in lines:
                try:
                    parsed_line = json.loads(line)
                    
                    # Extract different types of Codex responses
                    if parsed_line.get('role') == 'user':
                        # User input
                        if 'content' in parsed_line and parsed_line['content']:
                            content = parsed_line['content'][0].get('text', '')
                            parsed_response["claude_code_messages"].append({
                                "type": "user_input",
                                "content": content[:1000] + "..." if len(content) > 1000 else content
                            })
                    
                    elif parsed_line.get('role') == 'assistant' or parsed_line.get('status') == 'completed':
                        # Assistant response
                        if 'content' in parsed_line and parsed_line['content']:
                            content = parsed_line['content'][0].get('text', '')
                            parsed_response["claude_code_messages"].append({
                                "type": "assistant_response", 
                                "content": content
                            })
                            # This is the main response content
                            if content and not parsed_response["response_content"]:
                                parsed_response["response_content"] = content
                    
                    elif parsed_line.get('type') == 'function_call':
                        # Function call
                        func_call = {
                            "id": parsed_line.get('id', ''),
                            "name": parsed_line.get('name', ''),
                            "status": parsed_line.get('status', ''),
                            "arguments": parsed_line.get('arguments', '')
                        }
                        parsed_response["function_calls"].append(func_call)
                    
                    elif parsed_line.get('type') == 'function_call_output':
                        # Function call output
                        if parsed_response["function_calls"]:
                            call_id = parsed_line.get('call_id', '')
                            output = parsed_line.get('output', '')
                            # Find matching function call and add output
                            for func_call in parsed_response["function_calls"]:
                                if func_call.get('id', '').endswith(call_id.split('_')[-1]):
                                    func_call['output'] = output
                                    break
                    
                except json.JSONDecodeError:
                    continue
            
            return parsed_response
            
        except Exception as e:
            logger.error(f"Error parsing Claude Code response: {e}")
            return {
                "claude_code_messages": [],
                "response_content": raw_output[:2000] + "..." if len(raw_output) > 2000 else raw_output,
                "function_calls": [],
                "error": str(e)
            }
    
    def run_phase(self, phase: str, output_dir: Path) -> Dict[str, str]:
        logger.info(f"Running {phase} phase")
        
        # Create persistent workspace directory (like ChatDev's software directory)
        workspace_dir = output_dir / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize git repo to avoid warnings
        try:
            subprocess.run(["git", "init"], cwd=workspace_dir, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "codex@deveval.com"], cwd=workspace_dir, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.name", "Codex Agent"], cwd=workspace_dir, capture_output=True, check=True)
        except:
            pass  # Ignore git init errors
        
        # Setup workspace based on phase
        if phase == "Implementation":
            self.setup_workspace_for_implementation(workspace_dir)
        elif phase in ["UnitTesting", "AcceptanceTesting"]:
            self.setup_workspace_for_testing(workspace_dir, phase)
        else:
            raise ValueError(f"Unknown phase: {phase}")
        
        logger.info(f"Building unified prompt for {phase} phase")
        unified_prompt = self._build_unified_prompt(phase)
        
        logger.info(f"Built unified prompt for {phase} ({len(unified_prompt)} chars)")
        
        # Save prompt as Markdown (remove "unified" suffix)
        prompt_file = output_dir / f"prompt_{phase.lower()}.md"
        prompt_file.write_text(f"# {phase} Phase Prompt\n\n{unified_prompt}")
        logger.info(f"Saved prompt to: {prompt_file}")
        
        # Run Claude Code once with the unified prompt
        logger.info(f"Calling Claude Code with unified prompt for {phase}...")
        result = self.executor.run_claude_code(unified_prompt, workspace_dir)
        
        # Parse the raw output for better readability
        parsed_response = self._parse_claude_code_response(result["stdout"])
        
        # Save Claude Code output as JSON (remove "unified" suffix)
        output_data = {
            "phase": phase,
            "prompt_length": len(unified_prompt),
            "timestamp": datetime.now().isoformat(),
            "model": self.executor.model,
            "success": result["success"],
            "raw_output": result["stdout"],
            "parsed_response": parsed_response
        }
        
        if not result["success"]:
            output_data["error"] = result.get("error", "Unknown error")
            output_data["stderr"] = result.get("stderr", "")
            output_data["returncode"] = result.get("returncode", -1)
        
        output_file = output_dir / f"output_{phase.lower()}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved Claude Code output to: {output_file}")
        
        # Count generated files in workspace (but don't extract/parse from output)
        generated_files = self._count_generated_files(workspace_dir, phase)
        
        if result["success"]:
            logger.info(f"Claude Code call successful for {phase}")
        else:
            logger.error(f"Claude Code call failed for {phase}: {result.get('error', 'Unknown error')}")
        
        logger.info(f"Found {len(generated_files)} files in workspace")
        return generated_files
    
    def _count_generated_files(self, workspace_dir: Path, phase: str) -> Dict[str, str]:
        """Count files that were generated in the workspace by Claude Code."""
        generated_files = {}
        
        # Get expected files based on phase
        if phase == "Implementation":
            code_dag = self.repo_config.get("code_file_DAG", {})
            expected_files = list(code_dag.keys()) if isinstance(code_dag, dict) else code_dag
        elif phase == "UnitTesting":
            expected_files = list(self.repo_config.get("fine_unit_test_prompt", {}).keys())
        elif phase == "AcceptanceTesting":
            expected_files = list(self.repo_config.get("fine_acceptance_test_prompt", {}).keys())
        else:
            expected_files = []
        
        # Check if files exist in workspace
        for filename in expected_files:
            file_path = workspace_dir / filename
            if file_path.exists():
                try:
                    content = file_path.read_text()
                    generated_files[filename] = content
                    logger.info(f"Found generated file: {filename} ({len(content)} chars)")
                except Exception as e:
                    logger.warning(f"Error reading file {filename}: {e}")
        
        return generated_files
    
    def _build_unified_prompt(self, phase: str) -> str:        
        if phase == "Implementation":
            base_prompt = self.prompt_builder.build_implementation_prompt("")
            
        elif phase == "UnitTesting":
            # Build base prompt without specific filename
            base_prompt = self.prompt_builder.build_unit_testing_prompt("")
            
            # Add the entire fine_unit_test_prompt JSON, instead of one-by-one
            fine_prompts = self.repo_config.get("fine_unit_test_prompt", {})
            if fine_prompts:
                prompts_json = json.dumps(fine_prompts, indent=2)
                base_prompt = base_prompt.replace('Unit Test Prompt: ""', f'Unit Test Prompt: {prompts_json}')
            
        elif phase == "AcceptanceTesting":
            # Build base prompt without specific filename  
            base_prompt = self.prompt_builder.build_acceptance_testing_prompt("")
            
            # Add the entire fine_acceptance_test_prompt JSON, instead of one-by-one
            fine_prompts = self.repo_config.get("fine_acceptance_test_prompt", {})
            if fine_prompts:
                prompts_json = json.dumps(fine_prompts, indent=2)
                base_prompt = base_prompt.replace('Acceptance Test Prompt: ""', f'Acceptance Test Prompt: {prompts_json}')
        
        # base_prompt += "\n\n"
        # base_prompt += """You should write the code files in place. Double check you have written all the files as expected."""

        return base_prompt


def main():
    parser = argparse.ArgumentParser(description="Run DevEval with Claude Code using exact prompts and proper workspace setup")
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        choices=["Implementation", "UnitTesting", "AcceptanceTesting"],
        help="Task configuration to run"
    )
    parser.add_argument(
        "--input_path",
        type=str,
        required=True,
        help="Path to the DevEval project"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-3-5-sonnet-20241022",
        help="Model to use (default: claude-3-5-sonnet-20241022)"
    )
    parser.add_argument(
        "--review",
        type=str,
        default="none",
        choices=["none"],
        help="Review mode (only 'none' supported for Claude Code)"
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run evaluation after generation"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="WareHouse_claude_code",
        help="Output directory for results"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--livestream",
        action="store_true",
        help="Show real-time Claude Code output"
    )
    
    args = parser.parse_args()
    
    # Setup paths
    repo_path = Path(args.input_path).resolve()
    project_name = repo_path.name
    
    # Find config root (CompanyConfigNoReview directory)
    script_dir = Path(__file__).parent
    config_root = script_dir.parent / "CompanyConfigNoReview"
    
    if not config_root.exists():
        logger.error(f"Config directory not found: {config_root}")
        sys.exit(1)
    
    # Create output directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    output_path = Path(args.output_dir) / args.config / args.model / args.review / f"{args.model}_{project_name}_{args.config}_{timestamp}"
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Setup logging with different handlers for console and file
    # Root logger configuration
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='[%(asctime)s %(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            # Console handler with level based on --debug flag
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Always log everything to file regardless of debug flag
    log_file = output_path / f"run_{timestamp}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)  # Always DEBUG level for file
    file_handler.setFormatter(logging.Formatter('[%(asctime)s %(levelname)s] %(message)s'))
    logging.getLogger().addHandler(file_handler)
    
    logger.info(f"Starting Claude Code runner for {args.config} on {project_name}")
    logger.info(f"Repository path: {repo_path}")
    logger.info(f"Config root: {config_root}")
    logger.info(f"Output path: {output_path}")
    logger.debug(f"Debug mode: {'enabled' if args.debug else 'disabled'} (terminal only, log file always has full debug info)")
    
    try:
        # Initialize components
        executor = ClaudeCodeExecutor(args.model, args.livestream)
        runner = DevEvalClaudeCodeRunner(repo_path, config_root, executor)
        
        # Run the phase
        start_time = datetime.now()
        generated_files = runner.run_phase(args.config, output_path)
        end_time = datetime.now()
        
        # Save run summary as JSON
        summary = {
            "project": project_name,
            "config": args.config,
            "model": args.model,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "files_generated": len(generated_files),
            "generated_files": list(generated_files.keys()),
            "success": len(generated_files) > 0,
            "workspace_path": str(output_path / "workspace")
        }
        
        summary_file = output_path / "run_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Generated {len(generated_files)} files")
        logger.info(f"Workspace available at: {output_path / 'workspace'}")
        logger.info(f"Saved run summary to: {summary_file}")
        
        # Run evaluation if requested
        if args.evaluate and len(generated_files) > 0:
            logger.info("Running evaluation...")
            from evaluation import ClaudeCodeEvaluator
            
            evaluator = ClaudeCodeEvaluator(
                workspace_path=output_path / "workspace",
                repo_path=repo_path,
                language=runner.repo_config.get("language", "python")
            )
            
            eval_result = evaluator.evaluate(args.config)
            
            # Save evaluation results
            eval_file = output_path / "evaluation_result.json"
            with open(eval_file, 'w', encoding='utf-8') as f:
                json.dump(eval_result, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Evaluation completed. Success: {eval_result['success']}")
            logger.info(f"Evaluation results saved to: {eval_file}")
        
        logger.info("Claude Code runner completed successfully")
        
    except Exception as e:
        logger.error(f"Claude Code runner failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main() 