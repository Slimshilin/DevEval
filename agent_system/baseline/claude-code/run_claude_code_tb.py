#!/usr/bin/env python3
"""
Claude Code runner for all DevEval repositories and configurations.
Runs Implementation, UnitTesting, and AcceptanceTesting phases for all repositories
with progress tracking and resume functionality. Excludes TextCNN (GPU-required).
"""

import json
import sys
import argparse
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Set
from tqdm import tqdm
import traceback

# Setup logging with minimal verbosity
logging.basicConfig(
    level=logging.WARNING,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class ClaudeCodeBatchRunner:
    """Batch runner for extensive Claude Code experiments across all DevEval repos, excluding TextCNN."""
    
    def __init__(self, model: str = "claude-3-5-sonnet-20241022", output_dir: str = "WareHouse_claude_code_tb"):
        self.model = model
        self.output_dir = Path(output_dir)
        self.configs = ["Implementation", "UnitTesting", "AcceptanceTesting"]
        self.review = "none"
        
        # Get all repos excluding TextCNN
        self.repo_paths = self._get_all_repos()
        self.total_tasks = len(self.repo_paths) * len(self.configs)
        
        print(f"Found {len(self.repo_paths)} repositories")
        print(f"Total tasks: {self.total_tasks} ({len(self.configs)} configs × {len(self.repo_paths)} repos)")
        
        # Track results
        self.results = {
            "passed": [],
            "failed": [],
            "completed_tasks": 0,
            "total_tasks": self.total_tasks,
            "start_time": None,
            "end_time": None
        }
    
    def _get_all_repos(self) -> List[Path]:
        """Get all repository paths excluding TextCNN."""
        benchmark_data = Path(__file__).parent.parent.parent.parent / "benchmark_data"
        repo_paths = []
        
        # Find all repo_config.json files excluding TextCNN
        for config_file in benchmark_data.rglob("repo_config.json"):
            if "TextCNN" not in str(config_file):
                repo_paths.append(config_file.parent)
        
        # Sort by language and name for consistent ordering
        repo_paths.sort(key=lambda p: (p.parent.name, p.name))
        return repo_paths
    
    def _get_repo_info(self, repo_path: Path) -> Tuple[str, str]:
        """Extract language and repo name from path."""
        parts = repo_path.parts
        # Find benchmark_data index
        benchmark_idx = None
        for i, part in enumerate(parts):
            if part == "benchmark_data":
                benchmark_idx = i
                break
        
        if benchmark_idx is not None and benchmark_idx + 2 < len(parts):
            language = parts[benchmark_idx + 1]
            repo_name = parts[benchmark_idx + 2]
            return language, repo_name
        
        # Fallback
        return repo_path.parent.name, repo_path.name
    
    def _get_existing_results(self) -> Set[Tuple[str, str, str]]:
        """Get set of completed experiments (language, repo, config)."""
        completed = set()
        
        if not self.output_dir.exists():
            return completed
        
        # Scan output directory for completed experiments
        for config_dir in self.output_dir.iterdir():
            if not config_dir.is_dir() or config_dir.name not in self.configs:
                continue
                
            model_dir = config_dir / self.model / self.review
            if not model_dir.exists():
                continue
                
            for exp_dir in model_dir.iterdir():
                if not exp_dir.is_dir():
                    continue
                
                # Parse experiment directory name: {model}_{repo}_{config}_{timestamp}
                dir_parts = exp_dir.name.split('_')
                if len(dir_parts) >= 4:
                    # Extract repo name and config
                    config_part = dir_parts[-2]  # Second to last is config
                    repo_part = '_'.join(dir_parts[1:-2])  # Everything between model and config_timestamp
                    
                    # Check if experiment has run_summary.json (indicates completion)
                    summary_file = exp_dir / "run_summary.json"
                    if summary_file.exists():
                        try:
                            with open(summary_file, 'r') as f:
                                summary = json.load(f)
                                # Get language from project name or repo path
                                project_name = summary.get("project", repo_part)
                                
                                # Find corresponding repo to get language
                                for repo_path in self.repo_paths:
                                    language, repo_name = self._get_repo_info(repo_path)
                                    if repo_name == repo_part or project_name == repo_name:
                                        completed.add((language, repo_name, config_part))
                                        break
                        except Exception as e:
                            logger.debug(f"Error reading summary {summary_file}: {e}")
        
        return completed
    
    def _should_skip_experiment(self, language: str, repo_name: str, config: str, 
                               completed_experiments: Set[Tuple[str, str, str]]) -> bool:
        """Check if experiment should be skipped (already completed)."""
        return (language, repo_name, config) in completed_experiments
    
    def run_experiment(self, repo_path: Path, config: str) -> Dict:
        """Run a single experiment using run_claude_code_single.py."""
        language, repo_name = self._get_repo_info(repo_path)
        experiment_id = f"{language}-{repo_name}-{config}"
        
        try:
            # Prepare command to run single experiment
            script_path = Path(__file__).parent / "run_claude_code_single.py"
            cmd = [
                "python", str(script_path),
                "--config", config,
                "--input_path", str(repo_path),
                "--model", self.model,
                "--review", self.review,
                "--evaluate",  # Always run evaluation
                "--output_dir", str(self.output_dir)
            ]
            
            # Run the command
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # 10 minute timeout
            
            # Parse result from run_summary.json
            success = False
            files_generated = 0
            output_path = ""
            error = None
            
            if result.returncode == 0:
                # Find the most recent output directory for this experiment
                config_dir = self.output_dir / config / self.model / self.review
                if config_dir.exists():
                    # Get most recent directory matching pattern
                    pattern = f"{self.model}_{repo_name}_{config}_*"
                    matching_dirs = list(config_dir.glob(pattern))
                    if matching_dirs:
                        latest_dir = max(matching_dirs, key=lambda p: p.stat().st_mtime)
                        output_path = str(latest_dir)
                        
                        # Read evaluation_result.json for actual pass/fail
                        eval_file = latest_dir / "evaluation_result.json"
                        summary_file = latest_dir / "run_summary.json"
                        
                        if eval_file.exists():
                            with open(eval_file, 'r') as f:
                                eval_result = json.load(f)
                                success = eval_result.get("success", False)  # Based on evaluation
                        elif summary_file.exists():
                            with open(summary_file, 'r') as f:
                                summary = json.load(f)
                                success = summary.get("success", False)
                                
                        if summary_file.exists():
                            with open(summary_file, 'r') as f:
                                summary = json.load(f)
                                files_generated = summary.get("files_generated", 0)
            else:
                error = f"Command failed with return code {result.returncode}: {result.stderr}"
            
            return {
                "experiment_id": experiment_id,
                "language": language,
                "repo": repo_name,
                "config": config,
                "success": success,
                "files_generated": files_generated,
                "output_path": output_path,
                "error": error
            }
            
        except Exception as e:
            error_msg = f"Experiment {experiment_id} failed: {str(e)}"
            logger.error(error_msg)
            logger.debug(traceback.format_exc())
            
            return {
                "experiment_id": experiment_id,
                "language": language,
                "repo": repo_name,
                "config": config,
                "success": False,
                "files_generated": 0,
                "output_path": "",
                "error": error_msg
            }
    
    def run_all_experiments(self, continue_run: bool = True) -> Dict:
        """Run all experiments with progress tracking."""
        print(f"\n🚀 Starting Claude Code batch experiments ({self.model})")
        print(f"📁 Output directory: {self.output_dir}")
        print(f"📊 Total experiments: {self.total_tasks}")
        
        # Get completed experiments if continuing
        completed_experiments = set()
        if continue_run:
            completed_experiments = self._get_existing_results()
            if completed_experiments:
                print(f"✅ Found {len(completed_experiments)} completed experiments")
        
        # Filter tasks
        tasks_to_run = []
        for repo_path in self.repo_paths:
            language, repo_name = self._get_repo_info(repo_path)
            for config in self.configs:
                if not self._should_skip_experiment(language, repo_name, config, completed_experiments):
                    tasks_to_run.append((repo_path, config))
        
        print(f"📋 Running {len(tasks_to_run)} new experiments")
        if len(tasks_to_run) == 0:
            print("✨ All experiments already completed!")
            return self._generate_summary()
        
        self.results["start_time"] = datetime.now().isoformat()
        
        # Run experiments with progress bar
        with tqdm(total=len(tasks_to_run), desc="Running experiments", unit="exp") as pbar:
            for repo_path, config in tasks_to_run:
                language, repo_name = self._get_repo_info(repo_path)
                experiment_id = f"{language}-{repo_name}-{config}"
                
                pbar.set_description(f"Running {experiment_id}")
                
                result = self.run_experiment(repo_path, config)
                
                if result["success"]:
                    self.results["passed"].append(result)
                    status = "✅"
                else:
                    self.results["failed"].append(result)
                    status = "❌"
                
                self.results["completed_tasks"] += 1
                
                # Calculate real-time pass rate
                total_completed = len(self.results["passed"]) + len(self.results["failed"])
                pass_rate = (len(self.results["passed"]) / max(total_completed, 1)) * 100
                
                # Update progress bar with status and pass rate
                pbar.set_postfix({
                    "Status": status,
                    "Pass": len(self.results["passed"]),
                    "Fail": len(self.results["failed"]),
                    "Rate": f"{pass_rate:.1f}%"
                })
                pbar.update(1)
        
        self.results["end_time"] = datetime.now().isoformat()
        
        # Generate and save summary
        summary = self._generate_summary()
        self._save_summary(summary)
        
        return summary
    
    def _generate_summary(self) -> Dict:
        """Generate experiment summary."""
        # Get all results (including previously completed)
        all_completed = self._get_existing_results()
        
        total_completed = len(all_completed)
        pass_rate = (len(self.results["passed"]) / max(len(self.results["passed"]) + len(self.results["failed"]), 1)) * 100
        
        # Group results by language
        by_language = {}
        for result in self.results["passed"] + self.results["failed"]:
            lang = result["language"]
            if lang not in by_language:
                by_language[lang] = {"passed": 0, "failed": 0}
            
            if result["success"]:
                by_language[lang]["passed"] += 1
            else:
                by_language[lang]["failed"] += 1
        
        summary = {
            "model": self.model,
            "timestamp": datetime.now().isoformat(),
            "total_experiments": self.total_tasks,
            "completed_this_run": len(self.results["passed"]) + len(self.results["failed"]),
            "total_completed": total_completed,
            "pass_rate": f"{pass_rate:.1f}%",
            "results_this_run": {
                "passed": len(self.results["passed"]),
                "failed": len(self.results["failed"])
            },
            "by_language": by_language,
            "passed_experiments": [r["experiment_id"] for r in self.results["passed"]],
            "failed_experiments": [r["experiment_id"] for r in self.results["failed"]],
            "execution_time": self.results.get("start_time", ""),
            "detailed_results": self.results["passed"] + self.results["failed"]
        }
        
        return summary
    
    def _save_summary(self, summary: Dict):
        """Save summary to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_file = self.output_dir / f"claude_code_batch_summary_{timestamp}.json"
        
        # Ensure output directory exists
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Summary saved to: {summary_file}")
    
    def print_summary(self, summary: Dict):
        """Print formatted summary."""
        print(f"\n{'='*60}")
        print(f"🎯 CLAUDE CODE BATCH EXPERIMENT SUMMARY")
        print(f"{'='*60}")
        print(f"Model: {summary['model']}")
        print(f"Timestamp: {summary['timestamp']}")
        print(f"Total experiments: {summary['total_experiments']}")
        print(f"Completed this run: {summary['completed_this_run']}")
        print(f"Pass rate: {summary['pass_rate']}")
        
        print(f"\n📊 Results This Run:")
        print(f"  ✅ Passed: {summary['results_this_run']['passed']}")
        print(f"  ❌ Failed: {summary['results_this_run']['failed']}")
        
        if summary['by_language']:
            print(f"\n🌍 By Language:")
            for lang, stats in summary['by_language'].items():
                total = stats['passed'] + stats['failed']
                lang_pass_rate = (stats['passed'] / max(total, 1)) * 100
                print(f"  {lang}: {stats['passed']}/{total} ({lang_pass_rate:.1f}%)")
        
        if summary['passed_experiments']:
            print(f"\n✅ Passed Experiments:")
            for exp in summary['passed_experiments']:
                print(f"  • {exp}")
        
        if summary['failed_experiments']:
            print(f"\n❌ Failed Experiments:")
            for exp in summary['failed_experiments']:
                print(f"  • {exp}")


def main():
    parser = argparse.ArgumentParser(description="Run Claude Code batch experiments across all DevEval repositories (excludes TextCNN)")
    parser.add_argument(
        "--model",
        type=str,
        default="claude-3-5-sonnet-20241022",
        help="Model to use (default: claude-3-5-sonnet-20241022)"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="WareHouse_claude_code_tb",
        help="Output directory for results"
    )
    parser.add_argument(
        "--no-continue",
        action="store_true",
        help="Don't continue from previous run (start fresh)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Initialize and run batch experiments
        runner = ClaudeCodeBatchRunner(args.model, args.output_dir)
        summary = runner.run_all_experiments(continue_run=not args.no_continue)
        runner.print_summary(summary)
        
        print(f"\n🎉 Claude Code batch experiments completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Claude Code batch experiments failed: {e}")
        if args.debug:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()