import discord
from discord.ext import commands
import os
import aiosqlite
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DB_FILE = "leaderboard.db"

@bot.event
async def on_ready():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            data TEXT
        )
        """)
        await db.commit()
    print(f"{bot.user} is online!")

# Utility functions
async def get_setting(key):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_setting(key, value):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def get_owner_id():
    owner_id = await get_setting("owner_id")
    return int(owner_id) if owner_id else None

def is_owner():
    async def predicate(ctx):
        owner_id = await get_owner_id()
        return ctx.author.id == owner_id
    return commands.check(predicate)

# Command to set the owner
@bot.command()
@commands.is_owner()
async def setowner(ctx, member: discord.Member):
    await set_setting("owner_id", str(member.id))
    await ctx.send(f"{member.name} has been set as the new owner.")

# Command to set up fields
@bot.command()
@is_owner()
async def setup(ctx, *fields):
    await set_setting("fields", ",".join(fields))
    await ctx.send(f"Fields set: {', '.join(fields)}")

# Command to set ranking field
@bot.command()
@is_owner()
async def setrankby(ctx, field_name):
    fields = await get_setting("fields")
    if not fields:
        await ctx.send("Fields not set up yet.")
        return
    fields = fields.split(",")
    if field_name not in fields:
        await ctx.send("Invalid field name.")
        return
    await set_setting("rank_by", field_name)
    await ctx.send(f"Ranking field set to: {field_name}")

# Command to create leaderboard channel
@bot.command()
@is_owner()
async def setchannel(ctx, channel_name):
    guild = ctx.guild
    existing_channel = discord.utils.get(guild.channels, name=channel_name)
    if existing_channel:
        await set_setting("leaderboard_channel_id", str(existing_channel.id))
        await ctx.send(f"Leaderboard channel set to: {channel_name}")
    else:
        channel = await guild.create_text_channel(channel_name)
        await set_setting("leaderboard_channel_id", str(channel.id))
        await ctx.send(f"Created and set leaderboard channel: {channel_name}")

# Command for users to submit data via DM
@bot.command()
async def submit(ctx, *values):
    if not isinstance(ctx.channel, discord.DMChannel):
        return
    fields = await get_setting("fields")
    if not fields:
        await ctx.send("Fields not set up yet.")
        return
    fields = fields.split(",")
    if len(values) != len(fields):
        await ctx.send(f"Please provide exactly {len(fields)} values.")
        return
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "REPLACE INTO users (user_id, username, data) VALUES (?, ?, ?)",
            (str(ctx.author.id), ctx.author.name, ",".join(values))
        )
        await db.commit()
    await ctx.send("Data submitted!")

# Command to post leaderboard
@bot.command()
@is_owner()
async def leaderboard(ctx):
    fields = await get_setting("fields")
    rank_by = await get_setting("rank_by")
    channel_id = await get_setting("leaderboard_channel_id")
    if not fields or not rank_by or not channel_id:
        await ctx.send("Fields, ranking method, or leaderboard channel not set.")
        return
    fields = fields.split(",")
    rank_index = fields.index(rank_by)

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT username, data FROM users") as cursor:
            rows = await cursor.fetchall()

    users = []
    for name, data_str in rows:
        data = data_str.split(",")
        try:
            rank_value = int(data[rank_index])
        except ValueError:
            rank_value = 0
        users.append((name, data, rank_value))

    users.sort(key=lambda x: x[2], reverse=True)

    msg = f"**🏆 Leaderboard (by {rank_by})**\n"
    for i, (name, data, _) in enumerate(users, 1):
        msg += f"{i}. {name} - {', '.join(data)}\n"

    channel = bot.get_channel(int(channel_id))
    if channel:
        await channel.send(msg)
    else:
        await ctx.send("Invalid channel.")


bot.run(TOKEN)