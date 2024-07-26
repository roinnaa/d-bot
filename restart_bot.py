import os
import subprocess
import sys

def restart_bot():
    # Path to the bot script
    bot_script = "bot.py"
    # Restart the bot script
    subprocess.run([sys.executable, bot_script])

if __name__ == "__main__":
    restart_bot()