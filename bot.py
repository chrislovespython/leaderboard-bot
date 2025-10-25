import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from utils import db
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
    
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await db.init_db()
    await bot.tree.sync()
    for guild in bot.guilds:
        print(guild.id)
        await db.auto_add_admins_as_owners(guild)

class GuildSelect(discord.ui.Select):
    def __init__(self, user):
        self.user = user
        options = [
            discord.SelectOption(label=guild.name, value=str(guild.id))
            for guild in bot.guilds if guild.get_member(user.id)
        ]
        super().__init__(placeholder="Choose a guild", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("This selection isn't for you.", ephemeral=True)
            return
        self.view.guild_id = int(self.values[0])
        await interaction.response.defer()
        self.view.stop()

class GuildSelectView(discord.ui.View):
    def __init__(self, user):
        super().__init__()
        self.guild_id = None
        self.add_item(GuildSelect(user))

async def ensure_owner(guild_id, user_id):
    if not await db.has_owner(guild_id):
        await db.add_owner(guild_id, user_id)

@bot.tree.command(name="submit", description="Submit your score")
async def submit(interaction: discord.Interaction):
    if interaction.guild is not None:
        await interaction.response.send_message("❌ Please use this command in DMs.", ephemeral=True)
        return

    await interaction.response.send_message("🔹 Select the **guild** you're submitting for:", ephemeral=True)
    view = GuildSelectView(interaction.user)
    await interaction.followup.send("Please select a guild from the list below:", view=view)
    await view.wait()
    guild_id = view.guild_id

    if guild_id is None:
        await interaction.followup.send("❌ Guild selection was cancelled or timed out.", ephemeral=True)
        return

    await ensure_owner(guild_id, interaction.user.id)

    def check(m):
        return m.author == interaction.user and isinstance(m.channel, discord.DMChannel)

    try:
        await interaction.followup.send("🔹 Enter your **Username**:")
        username_msg = await bot.wait_for("message", check=check, timeout=120)

        await interaction.followup.send("🔹 Enter your **Score** (number):")
        score_msg = await bot.wait_for("message", check=check, timeout=120)

        await interaction.followup.send("🔹 Upload your **first image proof** (as an attachment):")
        img1_msg = await bot.wait_for("message", check=check, timeout=120)

        await interaction.followup.send("🔹 Upload your **second image proof** (as an attachment):")
        img2_msg = await bot.wait_for("message", check=check, timeout=120)

        if not img1_msg.attachments or not img2_msg.attachments:
            await interaction.followup.send("❌ You must upload both images as attachments.", ephemeral=True)
            return

        img1_url = img1_msg.attachments[0].url
        img2_url = img2_msg.attachments[0].url

        success = await db.add_submission(
            interaction.user.id,
            guild_id,
            username_msg.content.strip(),
            int(score_msg.content.strip()),
            img1_url,
            img2_url
        )

        if success:
            await interaction.followup.send("✅ Your submission was received and is pending review!", ephemeral=True)
            owners = await db.get_owners(guild_id)
            for owner_id in owners:
                owner = bot.get_user(owner_id)
                if owner:
                    try:
                        await owner.send(f"📥 New submission received from {interaction.user.mention} in guild ID {guild_id}.")
                    except discord.Forbidden:
                        print(f"Cannot send DM to {owner.name}.")
        else:
            await interaction.followup.send("❌ You've already submitted for this guild.", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"⚠️ Submission failed or timed out: {e}", ephemeral=True)

class ReviewView(discord.ui.View):
    def __init__(self, submission_id, user_id, images):
        super().__init__()
        self.submission_id = submission_id
        self.user_id = user_id
        self.images = images
        self.index = 0

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(self.images)
        embed = interaction.message.embeds[0]
        embed.set_image(url=self.images[self.index])
        await interaction.response.edit_message(embed=embed)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(self.images)
        embed = interaction.message.embeds[0]
        embed.set_image(url=self.images[self.index])
        await interaction.response.edit_message(embed=embed)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await db.approve_submission(self.submission_id)
        await interaction.response.send_message("✅ Submission approved.", ephemeral=True)
        user = bot.get_user(self.user_id)
        if user:
            try:
                await user.send("✅ Your submission has been approved!")
            except discord.Forbidden:
                print(f"Cannot send DM to {user.name}.")
        self.stop()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await db.reject_submission(self.submission_id)
        await interaction.response.send_message("❌ Submission rejected.", ephemeral=True)
        user = bot.get_user(self.user_id)
        if user:
            try:
                await user.send("❌ Your submission has been rejected.")
            except discord.Forbidden:
                print(f"Cannot send DM to {user.name}.")
        self.stop()

@bot.tree.command(name="review", description="Review pending submissions")
async def review(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if not await db.is_owner_or_reviewer(guild_id, interaction.user.id):
        await interaction.response.send_message("⛔ You're not authorized to review submissions.", ephemeral=True)
        return

    submissions = await db.get_pending_submissions(guild_id)
    if not submissions:
        await interaction.response.send_message("✅ No pending submissions found.", ephemeral=True)
        return

    for submission in submissions:
        sub_id, user_id, _, username, score, img1_url, img2_url, reviewed, timestamp = submission

        embed = discord.Embed(
            title=f"📝 Submission Review – #{sub_id}",
            description=(
                f"**Username**: `{username}`\n"
                f"**User ID**: `{user_id}`\n"
                f"**Score**: `{score}`\n"
                f"**Submitted at**: {timestamp}"
            ),
            color=discord.Color.teal()
        )
        embed.set_image(url=img1_url)
        embed.set_footer(text=f"Submission ID: {sub_id}")

        images = [img1_url, img2_url]
        view = ReviewView(submission_id=sub_id, user_id=user_id, images=images)

        try:
            await interaction.user.send(embed=embed, view=view)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I can't DM you the submissions. Please enable DMs from server members.", ephemeral=True)
            return

    await interaction.response.send_message("📬 Sent all pending submissions to your DMs.", ephemeral=True)
    
    
@bot.tree.command(name="banuser", description="Ban a user from the server")
@app_commands.describe(member="User to ban", reason="Reason for the ban")
@commands.has_permissions(ban_members=True)
async def banuser(ctx: discord.Interaction, member: discord.Member, reason:str="No reason provided"):
    try:
        # Try to send a DM first
        dm_message = f"You have been banned from {ctx.guild.name} for: {reason}"
        await member.send(dm_message)
    except discord.Forbidden:
        await ctx.response.send_message("Couldn't send DM to the user. Proceeding with ban.")

    await member.ban(reason=reason)
    await ctx.response.send_message(f"{member} has been banned.")

@bot.tree.command(name="addowner", description="Add a new owner who can review and manage settings.")
@app_commands.describe(user="User to add as an owner")
async def addowner(interaction: discord.Interaction, user: discord.Member):
    guild_id = interaction.guild.id
    if not await db.is_owner_or_reviewer(guild_id, interaction.user.id):
        await interaction.response.send_message("⛔ You're not authorized.", ephemeral=True)
        return

    await db.add_owner(guild_id, user.id)
    await interaction.response.send_message(f"✅ {user.mention} added as an owner.", ephemeral=True)

@bot.tree.command(name="removeowner", description="Remove an owner")
@app_commands.describe(user="User to remove from owners")
async def removeowner(interaction: discord.Interaction, user: discord.Member):
    guild_id = interaction.guild.id
    if not await db.is_owner_or_reviewer(guild_id, interaction.user.id):
        await interaction.response.send_message("⛔ You're not authorized.", ephemeral=True)
        return

    await db.remove_owner(guild_id, user.id)
    await interaction.response.send_message(f"✅ {user.mention} removed from owners.", ephemeral=True)

@bot.tree.command(name="setchannel", description="Set the channel where leaderboard will be posted")
@app_commands.describe(channel="Text channel to post leaderboard")
async def setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = interaction.guild.id
    if not await db.is_owner_or_reviewer(guild_id, interaction.user.id):
        await interaction.response.send_message("⛔ You're not authorized.", ephemeral=True)
        return

    await db.set_leaderboard_channel(guild_id, channel.id)
    await interaction.response.send_message(f"📢 Leaderboard channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="setleaderboardlimit", description="Set how many entries the leaderboard shows")
@app_commands.describe(limit="Maximum number of scores shown")
async def setleaderboardlimit(interaction: discord.Interaction, limit: int):
    if limit < 1:
        await interaction.response.send_message("❌ Limit must be at least 1.", ephemeral=True)
        return

    guild_id = interaction.guild.id
    if not await db.is_owner_or_reviewer(guild_id, interaction.user.id):
        await interaction.response.send_message("⛔ You're not authorized.", ephemeral=True)
        return

    await db.set_leaderboard_limit(guild_id, limit)
    await interaction.response.send_message(f"📊 Leaderboard will now show top {limit} scores.", ephemeral=True)

@bot.tree.command(name="post", description="Post the current leaderboard to the configured channel")
async def post(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if not await db.is_owner_or_reviewer(guild_id, interaction.user.id):
        await interaction.response.send_message("⛔ You're not authorized.", ephemeral=True)
        return

    settings = await db.get_settings(guild_id)
    if not settings or not settings.get("leaderboard_channel_id"):
        await interaction.response.send_message("⚙️ No leaderboard channel is set. Use `/setchannel` first.", ephemeral=True)
        return

    limit = settings.get("submission_limit", 10)
    channel_id = settings["leaderboard_channel_id"]
    print(f"Posting leaderboard to channel ID: {channel_id} with limit: {limit}")

    lb_data = await db.get_leaderboard(guild_id, limit)
    print(lb_data)
    if not lb_data:
        await interaction.response.send_message("📭 No leaderboard data found.", ephemeral=True)
        return

    embed = discord.Embed(title="🏆 Leaderboard", color=discord.Color.gold())
    for i, (username, score) in enumerate(lb_data, start=1):
        embed.add_field(name=f"{i}. {username}", value=f"Score: **{score}**", inline=False)

    channel = bot.get_channel(channel_id)
    if not channel:
        await interaction.response.send_message("❌ Could not find the configured leaderboard channel.", ephemeral=True)
        return

    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Leaderboard posted in {channel.mention}", ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("⛔ You don't have permission to run this command.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ An error occurred: `{error}`", ephemeral=True)


bot.run(TOKEN)

 
