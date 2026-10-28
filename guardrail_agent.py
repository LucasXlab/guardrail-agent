#!/usr/bin/env python3
"""Compatibility entry point; installs are optional for this source checkout."""

from guardrail_agent import *  # noqa: F403  (legacy single-file import facade)
from guardrail_agent.cli import run_cli

if __name__ == "__main__":
    run_cli()
