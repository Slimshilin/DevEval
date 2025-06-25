cd agent_sysyem/baseline
python codex/run_codex.py \
    --config UnitTesting \
    --input_path ../../benchmark_data/python/ArXiv_digest/ \
    --model o4-mini \
    --review none \
    --evaluate \
    --livestream \
    --debug