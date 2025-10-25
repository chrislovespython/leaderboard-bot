import discord

def leaderboard_embed(data, page=0, per_page=5):
    embed = discord.Embed(title="🏆 Leaderboard", color=discord.Color.gold())
    start = page * per_page
    end = start + per_page
    for i, entry in enumerate(data[start:end], start=start + 1):
        embed.add_field(name=f"{i}. {entry[0]}", value=f"Score: {entry[1]}", inline=False)
    embed.set_footer(text=f"Page {page + 1}")
    return embed
