#!/data/data/com.termux/files/usr/bin/bash

PID_FILE="$HOME/truthlayer-ai/logs/lifeos_ai.pid"

STOPPED=0

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")

    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping LifeOS AI by PID..."
        kill "$PID" 2>/dev/null
        sleep 2

        if kill -0 "$PID" 2>/dev/null; then
            echo "Force stopping LifeOS AI by PID..."
            kill -9 "$PID" 2>/dev/null
        fi

        STOPPED=1
    fi

    rm -f "$PID_FILE"
fi

LEFTOVER_PIDS=$(ps -ef | grep "python" | grep "app/bot.py" | grep -v grep | awk '{print $2}')

if [ -n "$LEFTOVER_PIDS" ]; then
    echo "Stopping leftover LifeOS AI process..."
    for P in $LEFTOVER_PIDS; do
        kill "$P" 2>/dev/null
    done

    sleep 2

    for P in $LEFTOVER_PIDS; do
        if kill -0 "$P" 2>/dev/null; then
            echo "Force stopping leftover process: $P"
            kill -9 "$P" 2>/dev/null
        fi
    done

    STOPPED=1
fi

rm -f "$PID_FILE"

if [ "$STOPPED" -eq 1 ]; then
    echo "LifeOS AI stopped."
else
    echo "LifeOS AI is not running."
fi
