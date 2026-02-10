#!/bin/bash
# Test runner for Apple TV subtitle detection issues
# Loads TMDB API key from .env and runs test cases

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Load environment variables
if [ -f ".env" ]; then
	export $(cat .env | xargs)
	echo "Loaded API key from .env"
else
	echo "Error: .env file not found in project root"
	exit 1
fi

# Check if TMDB_API_KEY is set
if [ -z "$TMDB_API_KEY" ]; then
	echo "Error: TMDB_API_KEY not set"
	exit 1
fi

# Enable debug logging
export PYTHONUNBUFFERED=1
export ITSUBDL_DEBUG=1

TEST_DIR="test"
mkdir -p "$TEST_DIR"

echo "=== Running Test Case 1: TMDB ID ==="
python3 -u -c "
import logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')
" && python3 -m itsubdl.cli 1228246 2>&1 | tee "$TEST_DIR/debug_tmdb.log" || true

echo ""
echo "=== Running Test Case 2: Direct Apple TV URL ==="
python3 -u -c "
import logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')
" && python3 -m itsubdl.cli "https://tv.apple.com/us/movie/five-nights-at-freddys-2/umc.cmc.4ers7f6sg3ia9ru4qhisv93yx" 2>&1 | tee "$TEST_DIR/debug_url.log" || true

echo ""
echo "Test logs saved to:"
echo "  - $TEST_DIR/debug_tmdb.log"
echo "  - $TEST_DIR/debug_url.log"
