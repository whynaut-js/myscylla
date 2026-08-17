import re
import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from utils.permissions import has_botperm

def _parse_amount(arg: str):
    """Returns (count, delta) — one will be None. Accepts plain numbers (50) or durations (1d, 2h, 30m, 1w)."""
    if arg.isdigit():
        return int(arg), None
    match = re.fullmatch(r"(\d+)([smhdw])", arg.lower())
    if not match:
        return None, None
    value, unit = match.groups()
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    return None, timedelta(seconds=int(value) * multipliers[unit])

class Purge(commands.Cog):
    """Message purging — by count, time window, author type, media, or a specific message."""

    def __init__(self, bot):
        self.bot = bot

    async def _run(self, ctx, amount_arg, check=None, label="message(s)"):
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "manage_channels"):
            await ctx.send("You don't have permission to purge.")
            return None

        count, delta = _parse_amount(amount_arg)
        if count is None and delta is None:
            await ctx.send("Give a number (e.g. `50`) or a duration (e.g. `1d`, `2h`, `30m`, `1w`).")
            return None

        try:
            await ctx.message.delete()
        except discord.NotFound:
            pass

        if delta:
            after = datetime.now(timezone.utc) - delta
            deleted = await ctx.channel.purge(limit=1000, after=after, check=check or (lambda m: True))
        else:
            deleted = await ctx.channel.purge(limit=count, check=check or (lambda m: True))

        msg = await ctx.send(f"Deleted {len(deleted)} {label}.")
        await msg.delete(delay=3)
        return deleted

    @commands.command(name="purge", aliases=["p", "P"])
    async def purge(self, ctx, amount: str):
        """Delete messages. Example: ~purge 50 or ~purge 1d"""
        await self._run(ctx, amount)

    @commands.command(name="botpurge", aliases=["bc"])
    async def botpurge(self, ctx, amount: str = "32"):
        """Delete bot messages AND messages that actually triggered a real command
        (checked via the bot's own parser, not just text matching — so a message like
        'kick him badly' is left alone since it never actually resolves to a command).
        Defaults to the last 32 if no amount given."""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "manage_channels"):
            await ctx.send("You don't have permission to purge.")
            return

        count, delta = _parse_amount(amount)
        if count is None and delta is None:
            await ctx.send("Give a number (e.g. `50`) or a duration (e.g. `1d`, `2h`, `30m`, `1w`).")
            return

        try:
            await ctx.message.delete()
        except discord.NotFound:
            pass

        history_kwargs = {"limit": 1000 if delta else count}
        if delta:
            history_kwargs["after"] = datetime.now(timezone.utc) - delta

        target_ids = set()
        async for message in ctx.channel.history(**history_kwargs):
            if message.author.bot:
                target_ids.add(message.id)
                continue
            try:
                msg_ctx = await self.bot.get_context(message)
            except Exception:
                continue
            if msg_ctx.command is not None:
                target_ids.add(message.id)

        if not target_ids:
            msg = await ctx.send("Nothing to delete — no bot messages or real commands found.")
            await msg.delete(delay=3)
            return

        deleted = await ctx.channel.purge(check=lambda m: m.id in target_ids, **history_kwargs)
        msg = await ctx.send(f"Deleted {len(deleted)} bot/command message(s).")
        await msg.delete(delay=3)

    @commands.command(name="humanpurge", aliases=["hp"])
    async def humanpurge(self, ctx, amount: str):
        """Delete only human messages."""
        await self._run(ctx, amount, check=lambda m: not m.author.bot, label="human message(s)")

    @commands.command(name="mediapurge", aliases=["mp"])
    async def mediapurge(self, ctx, amount: str):
        """Delete only messages with attachments or embeds."""
        await self._run(ctx, amount, check=lambda m: bool(m.attachments or m.embeds), label="media message(s)")

    @commands.command(name="nonmediapurge", aliases=["nmp"])
    async def nonmediapurge(self, ctx, amount: str):
        """Delete only messages without attachments or embeds."""
        await self._run(ctx, amount, check=lambda m: not (m.attachments or m.embeds), label="non-media message(s)")

    @commands.command(name="linkpurge", aliases=["lp"])
    async def linkpurge(self, ctx, amount: str):
        """Delete only messages containing a link."""
        url_pattern = re.compile(r"https?://\S+")
        await self._run(ctx, amount, check=lambda m: bool(url_pattern.search(m.content)), label="message(s) with links")

    @commands.command(name="userpurge", aliases=["up"])
    async def userpurge(self, ctx, member: discord.Member, amount: str):
        """Delete only a specific user's messages. Example: ~userpurge @user 50"""
        await self._run(ctx, amount, check=lambda m: m.author.id == member.id, label=f"message(s) from {member.display_name}")

    @commands.command(name="containspurge", aliases=["cp"])
    async def containspurge(self, ctx, amount: str, *, text: str):
        """Delete messages containing specific text. Example: ~containspurge 50 spam link"""
        needle = text.lower()
        await self._run(ctx, amount, check=lambda m: needle in m.content.lower(), label="matching message(s)")

    @commands.command(name="purgefrom", aliases=["pf"])
    async def purgefrom(self, ctx, message_id: int = None):
        """Delete everything after a message. Reply to a message, or give its ID."""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "manage_channels"):
            await ctx.send("You don't have permission to purge.")
            return

        target_id = message_id
        if target_id is None and ctx.message.reference:
            target_id = ctx.message.reference.message_id
        if target_id is None:
            await ctx.send("Reply to a message or give a message ID.")
            return

        try:
            target_msg = await ctx.channel.fetch_message(target_id)
        except discord.NotFound:
            await ctx.send("Couldn't find that message in this channel.")
            return

        try:
            await ctx.message.delete()
        except discord.NotFound:
            pass

        deleted = await ctx.channel.purge(limit=1000, after=target_msg)
        try:
            await target_msg.delete()
            deleted.append(target_msg)
        except discord.NotFound:
            pass

        msg = await ctx.send(f"Deleted {len(deleted)} message(s).")
        await msg.delete(delay=3)

async def setup(bot):
    await bot.add_cog(Purge(bot))
