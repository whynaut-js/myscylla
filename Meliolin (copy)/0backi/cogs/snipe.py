import discord
from collections import defaultdict, deque
from datetime import datetime, timezone
from discord.ext import commands
from utils.permissions import has_botperm
from utils.checks import is_owner
from utils.pagination import EntryPaginatorView

MAX_STORED = 5

class Snipe(commands.Cog):
    """Recover recently deleted messages, edited messages, and removed reactions per channel."""

    def __init__(self, bot):
        self.bot = bot
        self.deleted = defaultdict(lambda: deque(maxlen=MAX_STORED))
        self.edited = defaultdict(lambda: deque(maxlen=MAX_STORED))
        self.reactions_removed = defaultdict(lambda: deque(maxlen=MAX_STORED))

        self.owner_deleted = defaultdict(lambda: deque(maxlen=MAX_STORED))
        self.owner_edited = defaultdict(lambda: deque(maxlen=MAX_STORED))
        self.owner_reactions_removed = defaultdict(lambda: deque(maxlen=MAX_STORED))

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot and message.webhook_id is None:
            return
        entry = {
            "author": message.author,
            "content": message.content,
            "attachments": [a.url for a in message.attachments],
            "time": datetime.now(timezone.utc),
        }
        self.deleted[message.channel.id].appendleft(entry)
        self.owner_deleted[message.channel.id].appendleft(entry)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot:
            return
        if before.content == after.content:
            return
        entry = {
            "author": before.author,
            "before": before.content,
            "after": after.content,
            "time": datetime.now(timezone.utc),
            "jump_url": after.jump_url,
        }
        self.edited[before.channel.id].appendleft(entry)
        self.owner_edited[before.channel.id].appendleft(entry)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            return
        user = self.bot.get_user(payload.user_id)
        entry = {
            "user": user,
            "emoji": str(payload.emoji),
            "message_id": payload.message_id,
            "time": datetime.now(timezone.utc),
        }
        self.reactions_removed[payload.channel_id].appendleft(entry)
        self.owner_reactions_removed[payload.channel_id].appendleft(entry)

    def _build_deleted_embed(self, entry, index, total, tag=""):
        embed = discord.Embed(
            description=entry["content"] or "*(no text content)*",
            color=discord.Color.dark_red() if tag else discord.Color.orange(),
            timestamp=entry["time"],
        )
        embed.set_author(name=str(entry["author"]), icon_url=entry["author"].display_avatar.url)
        if entry["attachments"]:
            embed.add_field(name="Attachments", value="\n".join(entry["attachments"]), inline=False)
        embed.set_footer(text=f"{tag}Deleted message {index + 1}/{total}")
        return embed

    def _build_edited_embed(self, entry, index, total, tag=""):
        embed = discord.Embed(
            color=discord.Color.dark_gold() if tag else discord.Color.gold(),
            timestamp=entry["time"],
        )
        embed.set_author(name=str(entry["author"]), icon_url=entry["author"].display_avatar.url)
        embed.add_field(name="Before", value=entry["before"] or "*(empty)*", inline=False)
        embed.add_field(name="After", value=entry["after"] or "*(empty)*", inline=False)
        embed.set_footer(text=f"{tag}Edited message {index + 1}/{total}")
        return embed

    def _build_reaction_embed(self, entry, index, total, tag=""):
        user_text = str(entry["user"]) if entry["user"] else f"Unknown user ({entry['message_id']})"
        embed = discord.Embed(
            description=f"{user_text} removed {entry['emoji']}",
            color=discord.Color.dark_purple() if tag else discord.Color.purple(),
            timestamp=entry["time"],
        )
        embed.set_footer(text=f"{tag}Removed reaction {index + 1}/{total}")
        return embed

    @commands.command(name="snipe", aliases=["sn"])
    async def snipe(self, ctx):
        """Browse recently deleted messages in this channel with Back/Next buttons."""
        entries = list(self.deleted.get(ctx.channel.id, []))
        if not entries:
            await ctx.send("Nothing to snipe here.")
            return
        view = EntryPaginatorView(entries, lambda e, i, t: self._build_deleted_embed(e, i, t), ctx.author.id)
        await ctx.send(embed=view.make_embed(), view=view)

    @commands.command(name="editsnipe", aliases=["esn"])
    async def editsnipe(self, ctx):
        """Browse recently edited messages in this channel with Back/Next buttons."""
        entries = list(self.edited.get(ctx.channel.id, []))
        if not entries:
            await ctx.send("Nothing to editsnipe here.")
            return
        view = EntryPaginatorView(entries, lambda e, i, t: self._build_edited_embed(e, i, t), ctx.author.id)
        await ctx.send(embed=view.make_embed(), view=view)

    @commands.command(name="reactsnipe", aliases=["rsn"])
    async def reactsnipe(self, ctx):
        """Browse recently removed reactions in this channel with Back/Next buttons."""
        entries = list(self.reactions_removed.get(ctx.channel.id, []))
        if not entries:
            await ctx.send("Nothing to reactsnipe here.")
            return
        view = EntryPaginatorView(entries, lambda e, i, t: self._build_reaction_embed(e, i, t), ctx.author.id)
        await ctx.send(embed=view.make_embed(), view=view)

    @commands.command(name="clearsnipe", aliases=["csn"])
    async def clearsnipe(self, ctx):
        """Wipe all snipe data (deleted/edited/reactions) for this channel."""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "manage_channels"):
            await ctx.send("You don't have permission to clear snipe data.")
            return
        self.deleted.pop(ctx.channel.id, None)
        self.edited.pop(ctx.channel.id, None)
        self.reactions_removed.pop(ctx.channel.id, None)
        await ctx.send("Snipe data cleared for this channel.")

    @commands.command(name="lisisnipe", aliases=["lsn"], hidden=True)
    @is_owner()
    async def lisisnipe(self, ctx):
        """Owner-only: browse deleted messages even if normal snipe data was cleared."""
        entries = list(self.owner_deleted.get(ctx.channel.id, []))
        if not entries:
            await ctx.send("Nothing in lisisnipe history here.")
            return
        view = EntryPaginatorView(entries, lambda e, i, t: self._build_deleted_embed(e, i, t, tag="[Lisi] "), ctx.author.id)
        await ctx.send(embed=view.make_embed(), view=view)

    @commands.command(name="lisieditsnipe", aliases=["lesn"], hidden=True)
    @is_owner()
    async def lisieditsnipe(self, ctx):
        """Owner-only: browse edited messages even if normal snipe data was cleared."""
        entries = list(self.owner_edited.get(ctx.channel.id, []))
        if not entries:
            await ctx.send("Nothing in lisieditsnipe history here.")
            return
        view = EntryPaginatorView(entries, lambda e, i, t: self._build_edited_embed(e, i, t, tag="[Lisi] "), ctx.author.id)
        await ctx.send(embed=view.make_embed(), view=view)

    @commands.command(name="lisireactsnipe", aliases=["lrsn"], hidden=True)
    @is_owner()
    async def lisireactsnipe(self, ctx):
        """Owner-only: browse removed reactions even if normal snipe data was cleared."""
        entries = list(self.owner_reactions_removed.get(ctx.channel.id, []))
        if not entries:
            await ctx.send("Nothing in lisireactsnipe history here.")
            return
        view = EntryPaginatorView(entries, lambda e, i, t: self._build_reaction_embed(e, i, t, tag="[Lisi] "), ctx.author.id)
        await ctx.send(embed=view.make_embed(), view=view)

async def setup(bot):
    await bot.add_cog(Snipe(bot))
