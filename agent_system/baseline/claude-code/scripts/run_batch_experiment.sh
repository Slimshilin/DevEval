#!/bin/bash
# Claude Code batch experiment runner - calls run_claude_code_single.py for each repo
# Runs all 21 repos x 3 configs = 63 experiments with evaluation

cd agent_system/baseline
python claude-code/run_claude_code_tb.py --model claude-opus-4-20250514 --output_dir WareHouse_claude_code_tb_claude-opus-4