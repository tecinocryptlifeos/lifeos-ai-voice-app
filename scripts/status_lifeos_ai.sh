#!/data/data/com.termux/files/usr/bin/bash

PID_FILE="$HOME/truthlayer-ai/logs/lifeos_ai.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "LifeOS AI is not running."
    exit 0
fi

PID=$(cat "$PID_FILE")

if kill -0 "$PID" 2>/dev/null; then
    echo "LifeOS AI is running."
    echo "PID: $PID"
else
    echo "LifeOS AI is not running."
    echo "Removing old PID file."
    rm -f "$PID_FILE"
fi
