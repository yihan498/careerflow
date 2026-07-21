# Contributing

Contributions are welcome when they preserve the evidence, approval and privacy boundaries.

1. Create a focused branch.
2. Use only fictional fixtures. Never add a real resume or application record.
3. Add or update tests for workflow changes.
4. Run `python scripts/run_demo.py`, `pytest`, and `python scripts/privacy_check.py`.
5. Explain any workspace-schema or state-machine change in the pull request.

Provider adapters must not silently weaken approval, claim unsupported facts, or write credentials to disk.
