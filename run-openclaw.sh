#!/bin/bash

# Go to the directory where the script lives
cd "$(dirname "$0")" || exit 1

# Activate virtual environment
source venv/bin/activate || { echo "Failed to activate venv"; exit 1; }

# Run the report script
python3 openclaw_ftse_daily.py

# Deactivate venv
deactivate

# Optional: log success timestamp
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Report run completed" >> openclaw_cron.log
