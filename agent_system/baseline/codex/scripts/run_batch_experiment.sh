#!/bin/bash
# Codex batch experiment runner - calls run_codex_single.py for each repo
# Runs all 21 repos x 3 configs = 63 experiments with evaluation

cd agent_system/baseline
python codex/run_codex_tb.py --model o4-mini --output_dir WareHouse_codex_tb_o4-mini