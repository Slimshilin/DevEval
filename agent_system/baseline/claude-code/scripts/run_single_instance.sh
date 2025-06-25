cd agent_system/baseline
python claude-code/run_claude_code_single.py \
    --config UnitTesting \
    --input_path ../../benchmark_data/python/ArXiv_digest/ \
    --model claude-sonnet-4-20250514 \
    --review none \
    --evaluate \
    --livestream \
    --debug