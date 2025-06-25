"""
DevEval Prompt Builder for Codex Integration

This module extracts and builds the prompts that DevEval uses by:
1. Loading PhaseConfig.json templates from CompanyConfigNoReview
2. Building phase environment variables exactly like DevEval
3. Resolving placeholders with actual content from the source repo
4. Adapting the prompts to fit the needs for CLI agents like Codex

It supports the following phases:
- Implementation
- UnitTesting
- AcceptanceTesting
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class DevEvalPromptBuilder:
    """Builds exact DevEval prompts for Codex integration."""
    
    def __init__(self, repo_path: Path, config_root: Path):
        """
        Initialize the prompt builder.
        
        Args:
            repo_path: Path to the DevEval project repository
            config_root: Path to agent_system/baseline/CompanyConfigNoReview
        """
        self.repo_path = repo_path
        self.config_root = config_root
        self.repo_config = self._load_repo_config()
        
    def _load_repo_config(self) -> Dict[str, Any]:
        """Load repository configuration."""
        config_path = self.repo_path / "repo_config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"repo_config.json not found at {config_path}")
        
        with open(config_path, "r") as f:
            return json.load(f)
    
    def _safe_read_file(self, filename: str) -> str:
        """Safely read file content."""
        if not filename:
            return ""
        
        file_path = self.repo_path / filename
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return ""
        
        try:
            return file_path.read_text()
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return ""
    
    def _load_phase_config(self, phase: str) -> Dict[str, Any]:
        """Load PhaseConfig.json for the specified phase."""
        phase_config_path = self.config_root / phase / "PhaseConfig.json"
        if not phase_config_path.exists():
            raise FileNotFoundError(f"PhaseConfig.json not found at {phase_config_path}")
        
        with open(phase_config_path, "r") as f:
            return json.load(f)
    
    def build_implementation_prompt(self, filename: str) -> str:
        """Build exact Implementation phase prompt for the given filename."""
        logger.info(f"Building implementation prompt for {filename}")
        
        # Load phase configuration
        phase_config = self._load_phase_config("Implementation")
        coding_phase = phase_config.get("Coding", {})
        phase_prompt_template = coding_phase.get("phase_prompt", [])
        assistant_role_name = coding_phase.get("assistant_role_name", "Programmer")
        
        if not phase_prompt_template:
            raise ValueError("No phase_prompt found in Implementation/PhaseConfig.json")
        
        # Build environment variables like DevEval does
        env_dict = {
            "prd": self._safe_read_file(self.repo_config.get("PRD", "")),
            "uml_class": self._safe_read_file(self.repo_config.get("UML_class", "")),
            "uml_sequence": self._safe_read_file(self.repo_config.get("UML_sequence", "")),
            "architecture_design": self._safe_read_file(self.repo_config.get("architecture_design", "")),
            "next_code_filename": filename,
            "golden_plan": self._get_file_list_json(),
            "assistant_role": assistant_role_name,
        }
        
        # Filter and modify the phase prompt template
        if isinstance(phase_prompt_template, list):
            # Remove unwanted entries
            filtered_prompts = []
            for prompt in phase_prompt_template:
                # Skip these entries entirely
                if any(skip_phrase in prompt for skip_phrase in [
                    "Next File to Code:",
                    "Previous Codes:",
                    "Current Code:",
                    "Coding filename:"
                ]):
                    continue
                
                # Modify FileGenerationInstructions to remove specific sentence
                if "FileGenerationInstructions:" in prompt:
                    prompt = prompt.replace('The filenames are as follows: "{next_code_filename}".', '').strip()
                
                # Remove the execution feedback sentence
                if "The 'Execution Feedback' section contains output and error information from standard testing programs. This feedback should be used as a guide to identify and rectify any bugs in your code, with the ultimate goal of successfully passing the tests." in prompt:
                    prompt = prompt.replace("The 'Execution Feedback' section contains output and error information from standard testing programs. This feedback should be used as a guide to identify and rectify any bugs in your code, with the ultimate goal of successfully passing the tests.", "").strip()
                
                # Replace the responsibility sentence to remove file-specific focus
                if 'your responsibility is to write code according to the provided plan, focusing specifically on creating the file "{next_code_filename}"' in prompt:
                    prompt = prompt.replace('your responsibility is to write code according to the provided plan, focusing specifically on creating the file "{next_code_filename}"', 'your responsibility is to write code according to the provided plan')
                
                filtered_prompts.append(prompt)
            
            # Join with line breaks to preserve structure
            prompt_template = "\n".join(filtered_prompts)
        else:
            prompt_template = str(phase_prompt_template)
        
        # Replace placeholders with actual values using safe formatting
        resolved_prompt = self._safe_format(prompt_template, env_dict)
        
        logger.info(f"Built implementation prompt for {filename} ({len(resolved_prompt)} chars)")
        return resolved_prompt
    
    def build_unit_testing_prompt(self, filename: str) -> str:
        """Build exact UnitTesting phase prompt for the given filename."""
        logger.info(f"Building unit testing prompt for {filename}")
        
        # Load phase configuration
        phase_config = self._load_phase_config("UnitTesting")
        unit_test_phase = phase_config.get("UnitTestCoding", {})
        phase_prompt_template = unit_test_phase.get("phase_prompt", [])
        assistant_role_name = unit_test_phase.get("assistant_role_name", "Tester")
        
        if not phase_prompt_template:
            raise ValueError("No phase_prompt found in UnitTesting/PhaseConfig.json")
        
        # Get fine unit test prompt for this file
        fine_unit_test_prompts = self.repo_config.get("fine_unit_test_prompt", {})
        unit_test_prompt = fine_unit_test_prompts.get(filename, "")
        
        # Build environment variables like DevEval does
        env_dict = {
            "prd": self._safe_read_file(self.repo_config.get("PRD", "")),
            "uml_class": self._safe_read_file(self.repo_config.get("UML_class", "")),
            "uml_sequence": self._safe_read_file(self.repo_config.get("UML_sequence", "")),
            "architecture_design": self._safe_read_file(self.repo_config.get("architecture_design", "")),
            "codes": self._get_existing_codes(),
            "unit_test_prompt": unit_test_prompt,
            "filename": filename,
            "coding_prompt": "you should write a unit test code",
            "assistant_role": assistant_role_name,
        }
        
        # Filter and modify the phase prompt template
        if isinstance(phase_prompt_template, list):
            # Remove unwanted entries
            filtered_prompts = []
            for prompt in phase_prompt_template:
                # Skip these entries entirely
                if any(skip_phrase in prompt for skip_phrase in [
                    "Unit Test Codes:",
                    "Code Modification:",
                    "UnitTestCoding Filename:"
                ]):
                    continue
                
                # Modify FileGenerationInstructions to remove specific sentence
                if "FileGenerationInstructions:" in prompt:
                    prompt = prompt.replace('The filenames are as follows: "{filename}".', '').strip()
                
                filtered_prompts.append(prompt)
            
            # Join with line breaks to preserve structure
            prompt_template = "\n".join(filtered_prompts)
        else:
            prompt_template = str(phase_prompt_template)
        
        # Replace placeholders with actual values using safe formatting
        resolved_prompt = self._safe_format(prompt_template, env_dict)
        
        logger.info(f"Built unit testing prompt for {filename} ({len(resolved_prompt)} chars)")
        return resolved_prompt
    
    def build_acceptance_testing_prompt(self, filename: str) -> str:
        """Build exact AcceptanceTesting phase prompt for the given filename."""
        logger.info(f"Building acceptance testing prompt for {filename}")
        
        # Load phase configuration
        phase_config = self._load_phase_config("AcceptanceTesting")
        acceptance_test_phase = phase_config.get("AcceptanceTestCoding", {})
        phase_prompt_template = acceptance_test_phase.get("phase_prompt", [])
        assistant_role_name = acceptance_test_phase.get("assistant_role_name", "Tester")
        
        if not phase_prompt_template:
            raise ValueError("No phase_prompt found in AcceptanceTesting/PhaseConfig.json")
        
        # Get fine acceptance test prompt for this file
        fine_acceptance_test_prompts = self.repo_config.get("fine_acceptance_test_prompt", {})
        acceptance_test_prompt = fine_acceptance_test_prompts.get(filename, "")
        
        # Build environment variables like DevEval does
        env_dict = {
            "prd": self._safe_read_file(self.repo_config.get("PRD", "")),
            "uml_class": self._safe_read_file(self.repo_config.get("UML_class", "")),
            "uml_sequence": self._safe_read_file(self.repo_config.get("UML_sequence", "")),
            "architecture_design": self._safe_read_file(self.repo_config.get("architecture_design", "")),
            "codes": self._get_existing_codes(),
            "acceptance_test_prompt": acceptance_test_prompt,
            "filename": filename,
            "coding_prompt": "you should write an acceptance test code",
            "assistant_role": assistant_role_name,
        }
        
        # Filter and modify the phase prompt template
        if isinstance(phase_prompt_template, list):
            # Remove unwanted entries
            filtered_prompts = []
            for prompt in phase_prompt_template:
                # Skip these entries entirely
                if any(skip_phrase in prompt for skip_phrase in [
                    "AcceptanceTestCoding Filename:"
                ]):
                    continue
                
                # Modify FileGenerationInstructions to remove specific sentence
                if "FileGenerationInstructions:" in prompt:
                    prompt = prompt.replace('The filenames are as follows: "{filename}".', '').strip()
                
                filtered_prompts.append(prompt)
            
            # Join with line breaks to preserve structure
            prompt_template = "\n".join(filtered_prompts)
        else:
            prompt_template = str(phase_prompt_template)
        
        # Replace placeholders with actual values using safe formatting
        resolved_prompt = self._safe_format(prompt_template, env_dict)
        
        logger.info(f"Built acceptance testing prompt for {filename} ({len(resolved_prompt)} chars)")
        return resolved_prompt
    
    def get_files_for_phase(self, phase: str) -> List[str]:
        """Get list of files to generate for the specified phase."""
        if phase == "Implementation":
            return self._get_file_list()
        elif phase == "UnitTesting":
            fine_unit_test_prompts = self.repo_config.get("fine_unit_test_prompt", {})
            return list(fine_unit_test_prompts.keys())
        elif phase == "AcceptanceTesting":
            fine_acceptance_test_prompts = self.repo_config.get("fine_acceptance_test_prompt", {})
            return list(fine_acceptance_test_prompts.keys())
        else:
            raise ValueError(f"Unknown phase: {phase}")
    
    def _get_file_list(self) -> List[str]:
        """Get list of implementation files."""
        code_file_dag = self.repo_config.get("code_file_DAG", {})
        if isinstance(code_file_dag, dict):
            return list(code_file_dag.keys())
        else:
            return code_file_dag if code_file_dag else []
    
    def _get_file_list_json(self) -> str:
        """Get code_file_DAG as JSON string for golden_plan."""
        import json
        code_file_dag = self.repo_config.get("code_file_DAG", {})
        return json.dumps(code_file_dag, indent=2)
    
    def _get_existing_codes(self) -> str:
        """Get existing source code content."""
        files_list = self._get_file_list()
        
        code_content = []
        for filename in files_list:
            file_path = self.repo_path / filename
            if file_path.exists():
                try:
                    content = file_path.read_text()
                    lang = filename.split('.')[-1] if '.' in filename else "text"
                    code_content.append(
                        f"The content of file {filename} is:\n"
                        f"```{lang}\n{content}\n```\n\n"
                    )
                except Exception as e:
                    logger.error(f"Error reading {filename}: {e}")
        
        return "".join(code_content)
    
    def _safe_format(self, template: str, env_dict: Dict[str, Any]) -> str:
        """Safely format template with environment variables."""
        try:
            return template.format(**env_dict)
        except KeyError as e:
            logger.warning(f"Missing placeholder {e} in prompt template, using empty string")
            # Create a safe environment that returns empty strings for missing keys
            from string import Formatter
            formatter = Formatter()
            safe_env = dict(env_dict)
            for _literal_text, field_name, _format_spec, _conversion in formatter.parse(template):
                if field_name and field_name not in safe_env:
                    safe_env[field_name] = ""
            
            return template.format(**safe_env) 