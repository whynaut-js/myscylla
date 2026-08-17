import re
import discord
from discord.ext import commands
from config.owner import Me
from utils.checks import is_server_owner
from utils.webhook import get_relay_webhook
from utils.uwu_transform import uwu_transform, random_link_excuse, random_gif_caption, random_sticker_caption

URL_RE = re.compile(r"https?://\S+")


class Uwu(commands.Cog):
    """Curse people with uwu — cursed users get their messages auto-transformed.
    'uwu perm' is the ABILITY to curse others, granted separately from the
    curse itself. Owner-only shortcuts: 'urtuff' one-off uwufies a single
    message, 'so tuff' permanently curses the target."""

    def __init__(self, bot):
        self.bot = bot

    async def _owner_ids(self):
        ids = set(Me)
        if getattr(self.bot, "owner_id", None):
            ids.add(self.bot.owner_id)
        if getattr(self.bot, "owner_ids", None):
            ids |= self.bot.owner_ids
        return ids

    async def _can_curse(self, guild: discord.Guild, member: discord.Member) -> bool:
        if member.id == guild.owner_id:
            return True
        if member.id in Me or await self.bot.is_owner(member):
            return True
        row = await self.bot.db.fetchone(
            "SELECT 1 FROM uwu_permitted WHERE guild_id = ? AND user_id = ?",
            (guild.id, member.id),
        )
        return row is not None

    async def _is_cursed(self, guild_id, user_id):
        row = await self.bot.db.fetchone(
            "SELECT 1 FROM uwu_cursed WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        return row is not None

    def _is_gif(self, message: discord.Message) -> bool:
        for a in message.attachments:
            if a.filename.lower().endswith(".gif"):
                return True
        content_lower = message.content.lower()
        if "tenor.com" in content_lower or "giphy.com" in content_lower:
            return True
        return False

    async def _uwufy_message(self, message: discord.Message):
        try:
            webhook = await get_relay_webhook(self.bot, message.channel)
        except discord.HTTPException:
            webhook = None

        author = message.author

        if message.stickers:
            sticker_name = message.stickers[0].name
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            if webhook:
                try:
                    await webhook.send(
                        random_sticker_caption(sticker_name),
                        username=author.display_name,
                        avatar_url=author.display_avatar.url,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    pass
            return

        if self._is_gif(message):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            if webhook:
                try:
                    await webhook.send(
                        random_gif_caption(),
                        username=author.display_name,
                        avatar_url=author.display_avatar.url,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    pass
            return

        if URL_RE.search(message.content):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            try:
                await message.channel.send(random_link_excuse())
            except discord.Forbidden:
                pass
            return

        if not message.content.strip():
            return

        transformed = uwu_transform(message.content)
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        if webhook:
            try:
                await webhook.send(
                    transformed,
                    username=author.display_name,
                    avatar_url=author.display_avatar.url,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                pass

    async def _resolve_target_message(self, message: discord.Message):
        if message.reference and message.reference.message_id:
            try:
                return await message.channel.fetch_message(message.reference.message_id)
            except discord.NotFound:
                return None
        if message.mentions:
            target_member = message.mentions[0]
            async for m in message.channel.history(limit=50):
                if m.author.id == target_member.id and m.id != message.id:
                    return m
        return None

    async def _resolve_target_member(self, message: discord.Message):
        if message.reference and message.reference.message_id:
            try:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
                return ref_msg.author
            except discord.NotFound:
                return None
        if message.mentions:
            return message.mentions[0]
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.webhook_id is not None or message.guild is None:
            return

        owner_ids = await self._owner_ids()
        is_bot_owner = message.author.id in owner_ids
        content_stripped = message.content.strip().lower()

        if is_bot_owner and content_stripped in ("urtuff", "ur tuff"):
            target_message = await self._resolve_target_message(message)
            if target_message:
                await self._uwufy_message(target_message)
            return

        if is_bot_owner and content_stripped in ("so tuff", "sotuff"):
            target_member = await self._resolve_target_member(message)
            if target_member:
                await self.bot.db.execute(
                    "INSERT OR IGNORE INTO uwu_cursed (guild_id, user_id) VALUES (?, ?)",
                    (message.guild.id, target_member.id),
                )
            return

        if await self._is_cursed(message.guild.id, message.author.id):
            await self._uwufy_message(message)

    @commands.group(name="uwu", invoke_without_command=True)
    async def uwu(self, ctx):
        """Curse people with uwu, and manage who's allowed to curse others."""
        await ctx.send(
            "**Uwu commands:**\n"
            "`~uwu curse <@user>` — curse them (requires uwu perm)\n"
            "`~uwu uncurse <@user>` — remove their curse (requires uwu perm)\n"
            "`~uwu cursed` — view everyone currently cursed (requires uwu perm)\n"
            "`~uwu clearall` — remove ALL curses at once (server owner only)\n"
            "`~uwu perm add/remove <@user>` — grant/revoke who CAN curse others (server owner only)\n"
            "`~uwu perm list` — view everyone with curse permission (requires uwu perm)"
        )

    @uwu.group(name="perm", invoke_without_command=True)
    async def uwu_perm(self, ctx):
        """Manage who has permission to curse others with uwu."""
        await ctx.send("Usage: `~uwu perm add/remove/list <@user>`")

    @uwu_perm.command(name="add")
    @is_server_owner()
    async def uwu_perm_add(self, ctx, member: discord.Member):
        """Let a user curse others with uwu."""
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO uwu_permitted (guild_id, user_id) VALUES (?, ?)",
            (ctx.guild.id, member.id),
        )
        await ctx.send(f"{member.mention} can now curse others with uwu.")

    @uwu_perm.command(name="remove")
    @is_server_owner()
    async def uwu_perm_remove(self, ctx, member: discord.Member):
        """Revoke a user's ability to curse others."""
        await self.bot.db.execute(
            "DELETE FROM uwu_permitted WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, member.id),
        )
        await ctx.send(f"Removed {member.mention}'s uwu-curse permission.")

    @uwu_perm.command(name="list")
    async def uwu_perm_list(self, ctx):
        """View everyone with permission to curse others. Requires uwu perm."""
        if not await self._can_curse(ctx.guild, ctx.author):
            await ctx.send("You don't have permission to view this.")
            return
        rows = await self.bot.db.fetchall(
            "SELECT user_id FROM uwu_permitted WHERE guild_id = ?", (ctx.guild.id,)
        )
        if not rows:
            await ctx.send("No one has uwu-curse permission (besides the server/bot owner).")
            return
        lines = [f"<@{r[0]}>" for r in rows]
        await ctx.send("Users with uwu-curse permission:\n" + "\n".join(lines))

    @uwu.command(name="curse")
    async def uwu_curse(self, ctx, members: commands.Greedy[discord.Member]):
        """Curse one or more members with uwu — their future messages get uwufied."""
        if not await self._can_curse(ctx.guild, ctx.author):
            await ctx.send("You don't have permission to curse people with uwu.")
            return
        if not members:
            await ctx.send("Mention at least one member.")
            return
        for member in members:
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO uwu_cursed (guild_id, user_id) VALUES (?, ?)",
                (ctx.guild.id, member.id),
            )
        names = ", ".join(m.mention for m in members)
        await ctx.send(f"Cursed with uwu: {names}", allowed_mentions=discord.AllowedMentions.none())

    @uwu.command(name="uncurse")
    async def uwu_uncurse(self, ctx, members: commands.Greedy[discord.Member]):
        """Remove uwu curse from one or more members."""
        if not await self._can_curse(ctx.guild, ctx.author):
            await ctx.send("You don't have permission to remove uwu curses.")
            return
        if not members:
            await ctx.send("Mention at least one member.")
            return
        for member in members:
            await self.bot.db.execute(
                "DELETE FROM uwu_cursed WHERE guild_id = ? AND user_id = ?",
                (ctx.guild.id, member.id),
            )
        names = ", ".join(m.mention for m in members)
        await ctx.send(f"Freed from uwu curse: {names}", allowed_mentions=discord.AllowedMentions.none())

    @uwu.command(name="cursed")
    async def uwu_cursed_list(self, ctx):
        """View everyone currently cursed with uwu in this server. Requires uwu perm."""
        if not await self._can_curse(ctx.guild, ctx.author):
            await ctx.send("You don't have permission to view this.")
            return
        rows = await self.bot.db.fetchall(
            "SELECT user_id FROM uwu_cursed WHERE guild_id = ?", (ctx.guild.id,)
        )
        if not rows:
            await ctx.send("No one is currently cursed.")
            return
        lines = [f"<@{r[0]}>" for r in rows]
        await ctx.send("Cursed users:\n" + "\n".join(lines))

    @uwu.command(name="clearall")
    @is_server_owner()
    async def uwu_clear_all(self, ctx):
        """Remove ALL uwu curses in this server at once."""
        await self.bot.db.execute("DELETE FROM uwu_cursed WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send("All uwu curses cleared for this server.")

async def setup(bot):
    await bot.add_cog(Uwu(bot))
