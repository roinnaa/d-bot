import os
import nextcord
from nextcord.ext import commands
import sqlite3
from datetime import datetime, timedelta

# Read the bot token from environment variables
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Set up the bot and database
intents = nextcord.Intents.default()
intents.members = True
intents.message_content = True  # Enable message content intent

bot = commands.Bot(command_prefix="!", intents=intents)

# Connect to the SQLite database
conn = sqlite3.connect('clocking.db')
c = conn.cursor()

# Create a table if it doesn't exist
c.execute('''CREATE TABLE IF NOT EXISTS clocking
             (id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, timestamp TEXT)''')
conn.commit()

@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')

# Check if user has administrative privileges
def is_admin(user):
    return user.guild_permissions.administrator

# Slash command to clock in
@bot.slash_command(name="clockin", description="Clock in to start your shift")
async def clockin(interaction: nextcord.Interaction):
    user = interaction.user
    clocked_in_role_name = "Clocked In"

    user_id = user.id

    # Check if the user is already clocked in
    c.execute("""
        SELECT * FROM clocking 
        WHERE user_id = ? 
        AND action = 'clockin' 
        AND user_id NOT IN (
            SELECT user_id 
            FROM clocking 
            WHERE action = 'clockout' 
            AND timestamp > (
                SELECT timestamp 
                FROM clocking 
                WHERE user_id = clocking.user_id 
                AND action = 'clockin'
                ORDER BY timestamp DESC 
                LIMIT 1
            )
        )
    """, (user_id,))
    already_clocked_in = c.fetchone()

    if already_clocked_in:
        await interaction.response.send_message("You are already clocked in. Please clock out first before clocking in again.", ephemeral=True)
        return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    c.execute("INSERT INTO clocking (user_id, action, timestamp) VALUES (?, ?, ?)", 
              (user_id, 'clockin', timestamp))
    conn.commit()

    # Assign the 'Clocked In' role
    clocked_in_role = nextcord.utils.get(interaction.guild.roles, name=clocked_in_role_name)
    if clocked_in_role:
        await interaction.response.send_message("You are already clocked in. Please clock out first before clocking in again.", ephemeral=True)
        return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    c.execute("INSERT INTO clocking (user_id, action, timestamp) VALUES (?, ?, ?)", 
              (user_id, 'clockin', timestamp))
    conn.commit()

    # Assign the 'Clocked In' role
    clocked_in_role = nextcord.utils.get(interaction.guild.roles, name=clocked_in_role_name)
    if clocked_in_role:
        await user.add_roles(clocked_in_role)
    
    await interaction.response.send_message(f"{user.mention} clocked in at {timestamp}")

# Slash command to clock out
@bot.slash_command(name="clockout", description="Clock out to end your shift")
async def clockout(interaction: nextcord.Interaction):
    user = interaction.user
    clocked_in_role_name = "Clocked In"

    user_id = user.id
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    c.execute("INSERT INTO clocking (user_id, action, timestamp) VALUES (?, ?, ?)", 
              (user_id, 'clockout', timestamp))
    conn.commit()

    # Remove the 'Clocked In' role
    clocked_in_role = nextcord.utils.get(interaction.guild.roles, name=clocked_in_role_name)
    if clocked_in_role:
        await user.remove_roles(clocked_in_role)
    
    await interaction.response.send_message(f"{user.mention} clocked out at {timestamp}")

# Slash command to view logs
@bot.slash_command(name="logs", description="View clock-in and clock-out logs")
async def logs(interaction: nextcord.Interaction, user: nextcord.User = None):
    requesting_user = interaction.user

    if user:
        if not is_admin(requesting_user):
            await interaction.response.send_message("You do not have permission to view other users' logs.", ephemeral=True)
            return
    else:
        user = requesting_user

    user_id = user.id
    c.execute("SELECT action, timestamp FROM clocking WHERE user_id = ? ORDER BY timestamp", (user_id,))
    records = c.fetchall()
    
    if records:
        log_msg = "\n".join([f"{action} at {timestamp}" for action, timestamp in records])
        clockin_count = sum(1 for action, _ in records if action == 'clockin')
        clockout_count = sum(1 for action, _ in records if action == 'clockout')
        total_logs = len(records)

        # Calculate total logged minutes
        total_time = timedelta()
        clockin_time = None

        for action, timestamp in records:
            timestamp_dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            if action == 'clockin':
                clockin_time = timestamp_dt
            elif action == 'clockout' and clockin_time:
                total_time += timestamp_dt - clockin_time
                clockin_time = None

        total_minutes = total_time.total_seconds() / 60
        summary_msg = (f"\n\nTotal logs: {total_logs}\n"
                       f"Total clock-ins: {clockin_count}\n"
                       f"Total clock-outs: {clockout_count}\n"
                       f"Total logged minutes: {total_minutes:.2f}")
        await interaction.response.send_message(f"Logs for {user.mention}:\n{log_msg}{summary_msg}")
    else:
        await interaction.response.send_message("No logs found.")

# Slash command to show currently logged in users
@bot.slash_command(name="current", description="Show users currently logged in")
async def current(interaction: nextcord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    # Get users who have clocked in but not clocked out
    c.execute("""
        SELECT DISTINCT user_id 
        FROM clocking 
        WHERE action = 'clockin' 
        AND user_id NOT IN (
            SELECT user_id 
            FROM clocking 
            WHERE action = 'clockout' 
            AND timestamp > (
                SELECT timestamp 
                FROM clocking 
                WHERE user_id = clocking.user_id 
                AND action = 'clockin'
                ORDER BY timestamp DESC 
                LIMIT 1
            )
        )
    """)
    records = c.fetchall()

    if records:
        user_ids = list(set(record[0] for record in records))
        members = [interaction.guild.get_member(user_id) for user_id in user_ids]
        logged_in_users = [member.mention for member in members if member is not None]
        if logged_in_users:
            await interaction.response.send_message(f"Currently logged in users:\n" + "\n".join(logged_in_users))
        else:
            await interaction.response.send_message("No users are currently logged in.")
    else:
        await interaction.response.send_message("No users are currently logged in.")

# Slash command to shut down the bot
@bot.slash_command(name="shutdown", description="Shut down the bot (Admin only)")
async def shutdown(interaction: nextcord.Interaction):
    if is_admin(interaction.user):
        await interaction.response.send_message("Shutting down...", ephemeral=True)
        await bot.close()
    else:
        await interaction.response.send_message("You do not have permission to shut down the bot.", ephemeral=True)

# Run the bot
bot.run('Token')