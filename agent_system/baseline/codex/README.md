# Codex Integration for DevEval Tasks

This directory implements CLI agents using [Codex](https://github.com/openai/codex) to evaluate DevEval tasks. The implementation provides both single experiment runners and batch processing capabilities for comprehensive evaluation across DevEval repositories (tasks).

## Overview

This implementation enables Codex agents to perform software development tasks from the DevEval benchmark, including:
- **Implementation**: Generate source code based on requirements
- **UnitTesting**: Create unit tests for existing implementations  
- **AcceptanceTesting**: Develop acceptance tests for validation

The system includes several adaptations from the original DevEval framework:
- **Prompt adaptations**: Modified DevEval prompts for CLI agent compatibility
- **NoReview mode**: Only implemented the without-code-review phases
- **Focused evaluation**: Only three development phases (excluding software design and environment setup)
- **TextCNN exclusion**: GPU-required repositories are excluded for compatibility
- **Evaluation methodology**: Uses `resolved/total` instead of averaging weighted on code lines (same as [terminal-bench](https://github.com/laude-institute/terminal-bench) but different from the original DevEval paper for brevity)

## Installation

### Prerequisites

1. **DevEval Setup**: First, follow the DevEval dependency installation from the [main README](../../../README.md)

2. **Docker Environment**: It's recommended to operate inside the Docker container. See [Docker setup instructions](../../../wiki.md) for detailed guidance.

3. **Codex CLI**: Install the Codex CLI from [openai/codex](https://github.com/openai/codex):
   ```bash
   # Installation instructions will vary - refer to the official repository
   # Ensure the 'codex' command is available in your PATH
   ```

4. **API Key Setup**: Export your OpenAI API key in the Docker container:
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```

### Verification

Verify your setup:
```bash
codex --version
echo $OPENAI_API_KEY
```

## Usage

We recommend running experiments from this path:
```bash
cd agent_system/baseline
```

### Single Experiment Runner

For general use and individual experiments, use `run_codex_single.py`:

```bash
# Run Implementation phase
python run_codex_single.py \
    --config Implementation \
    --input_path ../../benchmark_data/python/ArXiv_digest/ \
    --model o4-mini \
    --review none \
    --evaluate

# Run UnitTesting phase  
python run_codex_single.py \
    --config UnitTesting \
    --input_path ../../benchmark_data/java/Actor_relationship_game/ \
    --model o4-mini \
    --review none \
    --evaluate \
    --livestream \
    --debug

# Run AcceptanceTesting phase  
python run_codex_single.py \
    --config AcceptanceTesting \
    --input_path ../../benchmark_data/java/Actor_relationship_game/ \
    --model o4-mini \
    --review none \
    --evaluate \
    --livestream \
    --debug
```

**Options:**
- `--config`: Phase to run (Implementation, UnitTesting, AcceptanceTesting)
- `--input_path`: Path to the DevEval project repository
- `--model`: OpenAI model to use (default: gpt-4)
- `--review`: Review mode (only 'none' supported)
- `--evaluate`: Run evaluation after generation
- `--livestream`: Show real-time Codex output
- `--debug`: Enable debug logging
- `--output_dir`: Custom output directory (optional)

### Batch Runner (Terminal-Bench Comparison)

For running experiments whose scores can be directly compared to terminal-bench's DevEval adapter, use the batch runner:

```bash
# Run all experiments across all repositories and phases
python codex/run_codex_tb.py \
    --model o4-mini \
    --output_dir WareHouse_codex_tb_o4-mini

# Or use the convenience script
./codex/scripts/run_batch_experiment.sh
```

The batch runner provides:
- **Progress tracking**: Real-time progress bars and statistics
- **Resume functionality**: Continue from interrupted runs
- **Comprehensive coverage**: All 21+ repositories × 3 phases
- **Result aggregation**: Automatic summary generation and pass/fail statistics

**Batch Runner Options:**
- `--model`: Model to use for all experiments
- `--output_dir`: Base output directory for results
- `--no-continue`: Start fresh instead of resuming previous runs
- `--debug`: Enable debug logging

## Adaptations from Original DevEval

This implementation includes several adaptations to make DevEval compatible with CLI agents:

1. **Prompt Modifications**: DevEval prompts are adapted to remove file-specific instructions and iterative feedback loops
2. **Unified Prompts**: Multiple file generation tasks are combined into single prompts for CLI efficiency (e.g., code_file_DAG and prompts for unit/acceptance tests are directly inputted as raw jsons specified in the `repo_config.json`)
3. **Workspace Setup**: Proper environment setup for each phase (dependencies, test files, etc.)
4. **NoReview Configuration**: Uses CompanyConfigNoReview settings with adaptations of 1 and 2.
5. **Evaluation Method**: Success based on test pass/fail rather than code line averaging

## Output Structure

Each experiment generates a structured output directory:

```
WareHouse_codex/
└── {Phase}/
    └── {model}/
        └── none/
            └── {model}_{project}_{phase}_{timestamp}/
                ├── workspace/                    # Agent's working directory
                │   ├── src/                     # Generated source code
                │   ├── tests/                   # Test files
                │   └── ...                      # Project files
                ├── prompt_{phase}.md            # Input prompt used
                ├── output_{phase}.json          # Raw Codex output
                ├── run_summary.json             # Experiment metadata
                ├── evaluation_result.json       # Test execution results
                └── run_{timestamp}.log          # Detailed execution log
```
**Note**:
- `Phase`: Implementation, UnitTesting, or AcceptanceTesting.
- "none": This corresponds to the NoReview mode to load PhaseConfig prompts.
- `project`: The repo on which the agents work

**Key Files:**
- `evaluation_result.json`: Contains pass/fail status and test output
- `run_summary.json`: Experiment metadata and file generation count
- `workspace/`: Complete project state after agent execution
- `run_{timestamp}.log`: Full execution log with debug information


## Troubleshooting

### Common Issues

1. **Codex CLI not found**:
   ```bash
   # Verify installation
   which codex
   # Reinstall if necessary
   ```

2. **API key issues**:
   ```bash
   # Check environment variable
   echo $OPENAI_API_KEY
   # Re-export if needed
   export OPENAI_API_KEY="your-key"
   ```

3. **Permission errors**:
   ```bash
   # Ensure proper permissions in Docker container
   chmod +x ./codex/scripts/*.sh
   ```

4. **Python Path (module not found)**
    ```bash
    # cd to the path where you want to PYTHONPATH
    export PYTHONPATH=$PWD
    ```

5. **Evaluation failures**: Check `evaluation_result.json` for detailed error messages

### Debug Mode
Use `--debug` flag for verbose logging and `--livestream` to see real-time Codex output:

```bash
python run_codex_single.py \
    --config Implementation \
    --input_path ../../benchmark_data/python/example/ \
    --debug \
    --livestream
``` 