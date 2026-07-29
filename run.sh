#!/usr/bin/env bash
set -e
# Run the Flask dev server on the pinned port 5002.
# Usage: ./run.sh

# Activate virtualenv if present
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export FLASK_APP=app.py
# Explicitly pin the port so the URL does not change
flask run --port 5002
