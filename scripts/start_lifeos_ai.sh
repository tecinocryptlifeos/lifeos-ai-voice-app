#!/data/data/com.termux/files/usr/bin/bash

cd $HOME/truthlayer-ai || exit 1

source $HOME/.truthlayer_env

echo "Starting LifeOS AI..."
echo "Log file: $HOME/truthlayer-ai/logs/lifeos_ai.log"

python -u app/bot.py 2>&1 | tee -a logs/lifeos_ai.log
