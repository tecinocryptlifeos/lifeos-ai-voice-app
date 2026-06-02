#!/data/data/com.termux/files/usr/bin/bash

cd $HOME/truthlayer-ai || exit 1

source $HOME/.truthlayer_env

PID_FILE="$HOME/truthlayer-ai/logs/lifeos_ai.pid"
LOG_FILE="$HOME/truthlayer-ai/logs/lifeos_ai.log"

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "LifeOS AI is already running."
        echo "PID: $OLD_PID"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

echo "Starting LifeOS AI in background..."

nohup python -u app/bot.py >> "$LOG_FILE" 2>&1 &

NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

echo "LifeOS AI started in background."
echo "PID: $NEW_PID"
echo "Log file: $LOG_FILE"
