import aiosqlite
import os

DB_PATH = os.path.join("data", "bot_data.db")

async def export_leaderboard(guild_id: int, filetype: str = "csv") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT username, score, timestamp FROM leaderboard
            WHERE guild_id=?
            ORDER BY score DESC
        """, (guild_id,)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        return None  # No data to export

    filename = f"leaderboard_{guild_id}.{filetype}"
    filepath = os.path.join("data", filename)

    if filetype == "csv":
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("Username,Score,Timestamp\n")
            for row in rows:
                f.write(f"{row[0]},{row[1]},{row[2]}\n")
    elif filetype == "txt":
        with open(filepath, "w", encoding="utf-8") as f:
            for i, row in enumerate(rows, start=1):
                f.write(f"{i}. {row[0]} - Score: {row[1]} - {row[2]}\n")
    else:
        return None

    return filepath
