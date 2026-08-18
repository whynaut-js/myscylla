import re
import random
import time
import discord
from discord.ext import commands, tasks
from utils.permissions import has_botperm

DISCORD_EPOCH = 1420070400000
GIVEAWAY_EMOJI = "🎉"

def _parse_duration(s: str):
    match = re.fullmatch(r"(\d+)([smhdw])", s.lower())
    if not match:
        return None
    value, unit = match.groups()
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    return int(value) * multipliers[unit]

def _snowflake_to_ms(snowflake: int) -> int:
    return (snowflake >> 22) + DISCORD_EPOCH

def _format_delta(seconds: int) -> str:
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{days}d:{hours}h:{minutes}m:{secs}s"

class Giveaway(commands.Cog):
    """Full giveaway system (start/end/reroll/list) plus a snowflake-delay lookup tool — all in one place."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        await self.bot.db.execute(
            """
            CREATE TABLE IF NOT EXISTS giveaways (
                giveaway_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                channel_id INTEGER,
                message_id INTEGER,
                prize TEXT,
                winner_count INTEGER,
                end_time INTEGER,
                host_id INTEGER,
                ended INTEGER DEFAULT 0
            )
            """
        )
        self.check_giveaways.start()

    async def cog_unload(self):
        self.check_giveaways.cancel()

    async def _check(self, ctx):
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "manage_channels"):
            await ctx.send("You don't have permission to manage giveaways.")
            return False
        return True

    async def _get_winners(self, message: discord.Message, count: int):
        for reaction in message.reactions:
            if str(reaction.emoji) == GIVEAWAY_EMOJI:
                users = [u async for u in reaction.users() if not u.bot]
                if not users:
                    return []
                return random.sample(users, min(count, len(users)))
        return []

    async def _end_giveaway(self, row):
        giveaway_id, guild_id, channel_id, message_id, prize, winner_count, end_time, host_id, ended = row

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await self.bot.db.execute("UPDATE giveaways SET ended = 1 WHERE giveaway_id = ?", (giveaway_id,))
            return

        channel = guild.get_channel(channel_id)
        if channel is None:
            await self.bot.db.execute("UPDATE giveaways SET ended = 1 WHERE giveaway_id = ?", (giveaway_id,))
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await self.bot.db.execute("UPDATE giveaways SET ended = 1 WHERE giveaway_id = ?", (giveaway_id,))
            return

        winners = await self._get_winners(message, winner_count)

        embed = message.embeds[0] if message.embeds else discord.Embed(title=prize)
        embed.color = discord.Color.dark_grey()
        embed.description = f"🎉 Giveaway ended!\n**Prize:** {prize}"
        if winners:
            embed.add_field(name="Winner(s)", value=", ".join(w.mention for w in winners), inline=False)
        else:
            embed.add_field(name="Winner(s)", value="No valid entries.", inline=False)
        await message.edit(embed=embed)

        if winners:
            await channel.send(
                f"🎉 Congratulations {', '.join(w.mention for w in winners)}! You won **{prize}**!",
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        else:
            await channel.send(f"No valid entries — **{prize}** giveaway ended with no winner.")

        await self.bot.db.execute("UPDATE giveaways SET ended = 1 WHERE giveaway_id = ?", (giveaway_id,))

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        now = int(time.time())
        rows = await self.bot.db.fetchall(
            "SELECT * FROM giveaways WHERE ended = 0 AND end_time <= ?", (now,)
        )
        for row in rows:
            await self._end_giveaway(row)

    @check_giveaways.before_loop
    async def before_check_giveaways(self):
        await self.bot.wait_until_ready()

    @commands.group(invoke_without_command=True, aliases=["gw"])
    async def giveaway(self, ctx):
        """Giveaway system."""
        await ctx.send(
            "**Giveaway commands:**\n"
            "`~gw start <duration> <winners> <prize>` — Example: `~gw start 1h 1 Nitro`\n"
            "`~gw end <message_id>` — end early and pick winner(s) now\n"
            "`~gw reroll <message_id>` — pick new winner(s) from an ended giveaway\n"
            "`~gw list` — show active giveaways in this server\n\n"
            "**Snowflake delay tool:**\n"
            "`~snowflakedelay <id1> <id2>` (`~sfdelay`) — time between any two Discord IDs, formatted d:h:m:s"
        )

    @giveaway.command(name="start")
    async def gw_start(self, ctx, duration: str, winner_count: int, *, prize: str):
        """Start a giveaway. Example: ~gw start 1h 1 Nitro Classic"""
        if not await self._check(ctx):
            return

        seconds = _parse_duration(duration)
        if seconds is None:
            await ctx.send("Invalid duration. Use formats like `30s`, `10m`, `1h`, `2d`, `1w`.")
            return
        if winner_count < 1:
            await ctx.send("Winner count must be at least 1.")
            return

        end_time = int(time.time()) + seconds
        embed = discord.Embed(
            title="🎉 Giveaway!",
            description=(
                f"**Prize:** {prize}\n"
                f"**Winners:** {winner_count}\n"
                f"**Ends:** <t:{end_time}:R>\n"
                f"**Hosted by:** {ctx.author.mention}\n\n"
                f"React with {GIVEAWAY_EMOJI} to enter!"
            ),
            color=discord.Color.blurple(),
        )
        message = await ctx.send(embed=embed)
        await message.add_reaction(GIVEAWAY_EMOJI)

        await self.bot.db.execute(
            """
            INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winner_count, end_time, host_id, ended)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (ctx.guild.id, ctx.channel.id, message.id, prize, winner_count, end_time, ctx.author.id),
        )

    @giveaway.command(name="end")
    async def gw_end(self, ctx, message_id: int):
        """End a giveaway early and pick winner(s) immediately."""
        if not await self._check(ctx):
            return

        row = await self.bot.db.fetchone(
            "SELECT * FROM giveaways WHERE message_id = ? AND guild_id = ? AND ended = 0",
            (message_id, ctx.guild.id),
        )
        if row is None:
            await ctx.send("No active giveaway found with that message ID.")
            return

        await self._end_giveaway(row)
        await ctx.send("Giveaway ended.")

    @giveaway.command(name="reroll")
    async def gw_reroll(self, ctx, message_id: int):
        """Reroll winner(s) for an already-ended giveaway."""
        if not await self._check(ctx):
            return

        row = await self.bot.db.fetchone(
            "SELECT * FROM giveaways WHERE message_id = ? AND guild_id = ? AND ended = 1",
            (message_id, ctx.guild.id),
        )
        if row is None:
            await ctx.send("No ended giveaway found with that message ID (must already be ended to reroll).")
            return

        _, _, channel_id, _, prize, winner_count, _, _, _ = row
        channel = ctx.guild.get_channel(channel_id)
        if channel is None:
            await ctx.send("Couldn't find the original channel.")
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send("Couldn't find the original message.")
            return

        winners = await self._get_winners(message, winner_count)
        if not winners:
            await ctx.send("No valid entries to reroll from.")
            return

        await channel.send(
            f"🎉 New winner(s) for **{prize}**: {', '.join(w.mention for w in winners)}!",
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    @giveaway.command(name="list")
    async def gw_list(self, ctx):
        """List all active giveaways in this server."""
        rows = await self.bot.db.fetchall(
            "SELECT message_id, channel_id, prize, end_time FROM giveaways WHERE guild_id = ? AND ended = 0",
            (ctx.guild.id,),
        )
        if not rows:
            await ctx.send("No active giveaways.")
            return

        lines = []
        for message_id, channel_id, prize, end_time in rows:
            lines.append(f"**{prize}** — <#{channel_id}> — ends <t:{end_time}:R> — ID `{message_id}`")
        await ctx.send("\n".join(lines))

    @commands.command(name="snowflakedelay", aliases=["sfdelay", "msgdelay"])
    async def snowflakedelay(self, ctx, id1: int, id2: int):
        """Time between any two Discord IDs (message, user, channel, etc). Example: ~sfdelay 123... 456..."""
        ms1 = _snowflake_to_ms(id1)
        ms2 = _snowflake_to_ms(id2)
        diff_seconds = abs(ms2 - ms1) // 1000
        await ctx.send(f"Delay between those two IDs: `{_format_delta(diff_seconds)}`")

async def setup(bot):
    await bot.add_cog(Giveaway(bot))
