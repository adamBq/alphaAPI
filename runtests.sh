#!/bin/bash
set -e

# Create venv if it doesn't exist

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Install requirements and run tests inside the activated venv
. .venv/bin/activate
pip install --quiet -r requirements.txt
    
# Run tests using the venv's python
python -m pytest --cov=. --cov-report=xml --cov-report=html --junitxml=pytest-report.xml -rw
