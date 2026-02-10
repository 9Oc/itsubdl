#!/usr/bin/env python3
"""
Test runner for Apple TV subtitle detection
Enables debug logging and captures output
"""

import logging
import os
import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Load TMDB API key from .env
env_file = project_root / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            if line.startswith("TMDB_API_KEY"):
                key = line.strip().split("=")[1]
                os.environ["TMDB_API_KEY"] = key

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

# Now run the test
if __name__ == "__main__":
    import asyncio
    from itsubdl import cli

    test_input = sys.argv[1] if len(sys.argv) > 1 else "1228246"
    print(f"\n=== Testing with input: {test_input} ===\n")
    asyncio.run(cli.main(test_input))
