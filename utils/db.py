import aiosqlite
import os
from datetime import datetime

DB_PATH = os.path.join("data", "data.db")

async def init_db():
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                username TEXT,
                score INTEGER,
                image1_url TEXT,
                image2_url TEXT,
                reviewed INTEGER DEFAULT 0,
                timestamp TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS leaderboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                username TEXT,
                score INTEGER,
                timestamp TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS owners (
                guild_id INTEGER,
                user_id INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS reviewers (
                guild_id INTEGER,
                user_id INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                guild_id INTEGER PRIMARY KEY,
                leaderboard_channel_id INTEGER,
                submission_limit INTEGER DEFAULT 10
            )
        ''')
        await db.commit()

async def has_owner(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM owners WHERE guild_id=? LIMIT 1", (guild_id,)) as cur:
            return await cur.fetchone() is not None

async def add_owner(guild_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO owners (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
        await db.commit()

async def remove_owner(guild_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM owners WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        await db.commit()

async def get_owners(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM owners WHERE guild_id=?", (guild_id,)) as cursor:
            return [row[0] for row in await cursor.fetchall()]

async def is_owner_or_reviewer(guild_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM owners WHERE guild_id=? AND user_id=?", (guild_id, user_id)) as cur:
            if await cur.fetchone():
                return True
        async with db.execute("SELECT 1 FROM reviewers WHERE guild_id=? AND user_id=?", (guild_id, user_id)) as cur:
            return await cur.fetchone() is not None

async def add_submission(user_id, guild_id, username, score, image1, image2):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM submissions WHERE user_id=? AND guild_id=?", (user_id, guild_id)) as cursor:
            if await cursor.fetchone():
                return False
        await db.execute('''
            INSERT INTO submissions (user_id, guild_id, username, score, image1_url, image2_url, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, guild_id, username, score, image1, image2, datetime.utcnow().isoformat()))
        await db.commit()
        return True

async def get_pending_submissions(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM submissions WHERE guild_id=? AND reviewed=0", (guild_id,)) as cursor:
            return await cursor.fetchall()

async def approve_submission(submission_id):
    async with aiosqlite.connect(DB_PATH) as db:
        # Get data first
        async with db.execute("SELECT user_id, guild_id, username, score, timestamp FROM submissions WHERE id=?", (submission_id,)) as cursor:
            row = await cursor.fetchone()
        if row:
            await db.execute('''
                INSERT INTO leaderboard (user_id, guild_id, username, score, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', row)
        await db.execute("DELETE FROM submissions WHERE id=?", (submission_id,))
        await db.commit()

async def reject_submission(submission_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM submissions WHERE id=?", (submission_id,))
        await db.commit()

async def get_leaderboard(guild_id, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT username, score FROM leaderboard
            WHERE guild_id=?
            ORDER BY score DESC
            LIMIT ?
        ''', (guild_id, limit)) as cursor:
            return await cursor.fetchall()

async def set_leaderboard_channel(guild_id, channel_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO settings (guild_id, leaderboard_channel_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET leaderboard_channel_id=excluded.leaderboard_channel_id
        """, (guild_id, channel_id))
        await db.commit()

async def set_submission_limit(guild_id, limit):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO settings (guild_id, submission_limit)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET submission_limit=excluded.submission_limit
        """, (guild_id, limit))
        await db.commit()
        
async def auto_add_admins_as_owners(guild):
    async with aiosqlite.connect(DB_PATH) as db:
        owner_id = str(guild.owner_id)
        print(owner_id)
        await db.execute("INSERT OR IGNORE INTO owners (guild_id, user_id) VALUES (?, ?)", (guild.id, owner_id))
        print("Added Member to admins")
        await db.commit()

async def get_settings(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT leaderboard_channel_id, submission_limit FROM settings WHERE guild_id=?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"leaderboard_channel_id": row[0], "submission_limit": row[1]}
            else:
                return {}


async def set_leaderboard_limit(guild_id, limit):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO settings (guild_id, submission_limit)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET submission_limit=excluded.submission_limit
        """, (guild_id, limit))
        await db.commit()
