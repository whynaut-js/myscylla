import discord
from discord.ext import commands
from utils.permissions import has_botperm
from utils.confirm import ask_confirm
from utils import antinuke as an

PERM_ALIASES = {
    "view": "view_channel",
    "send": "send_messages",
    "react": "add_reactions",
    "embed": "embed_links",
    "attach": "attach_files",
    "connect": "connect",
    "speak": "speak",
    "manage": "manage_messages",
    "mentioneveryone": "mention_everyone",
    "history": "read_message_history",
}

class Channels(commands.Cog):
    """Full channel management — create, delete, rename, lock, slowmode, category, permissions, nuke, copy."""

    def __init__(self, bot):
        self.bot = bot

    async def _check(self, ctx):
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "manage_channels"):
            await ctx.send("You don't have permission to manage channels.")
            return False
        return True

    async def _antinuke_check(self, ctx):
        from cogs.antinuke import antinuke_admin_check
        predicate = antinuke_admin_check().predicate
        try:
            return await predicate(ctx)
        except commands.CheckFailure:
            await ctx.send("This requires antinuke admin or higher.")
            return False

    @commands.group(invoke_without_command=True, aliases=["ch"])
    async def channel(self, ctx):
        """Manage channels."""
        await ctx.send(
            "**Channel commands** (work nested `~channel <sub>` or standalone shortcut):\n"
            "`~channel create <name> [category]` — `~cc`\n"
            "`~channel delete <#channel>` — `~cd` (asks to confirm)\n"
            "`~channel rename <#channel> <new name>` — `~crn`\n"
            "`~channel lock [#channel]` — `~lock`\n"
            "`~channel unlock [#channel]` — `~unlock`\n"
            "`~channel slowmode <seconds> [#channel]` — `~slow`\n"
            "`~channel category <#channel> <category name>` — `~ccat`\n"
            "`~channel perms <#channel> <@user/@role> <allow/deny/reset> <perm>` — `~cperms`\n"
            "`~channel nuke [#channel]` — `~nuke` (antinuke admin+, asks to confirm)\n"
            "`~channel copy [#channel]` — `~copy` (antinuke admin+)\n\n"
            f"Valid perms: {', '.join(sorted(PERM_ALIASES.keys()))} (or any real Discord permission name)"
        )

    @channel.command(name="create", aliases=["cc"])
    async def channel_create(self, ctx, name: str, *, category: str = None):
        """Create a text channel, optionally inside a category."""
        if not await self._check(ctx):
            return
        if not await an.check_and_track(self.bot, ctx, "channel_create", "Mass channel creation"):
            return

        cat_obj = None
        if category:
            cat_obj = discord.utils.find(lambda c: c.name.lower() == category.lower(), ctx.guild.categories)
            if cat_obj is None:
                await ctx.send(f"Couldn't find category `{category}` — creating without one.")

        new_channel = await ctx.guild.create_text_channel(name, category=cat_obj, reason=f"Created by {ctx.author}")
        await ctx.send(f"Created {new_channel.mention}.")

    @channel.command(name="delete", aliases=["cd"])
    async def channel_delete(self, ctx, target: discord.TextChannel = None):
        """Delete a channel. Defaults to the current channel if none given. Requires confirmation."""
        if not await self._check(ctx):
            return

        target = target or ctx.channel
        if not await ask_confirm(ctx, f"⚠️ Delete {target.mention}? This **cannot** be undone."):
            await ctx.send("Cancelled.")
            return

        if not await an.check_and_track(self.bot, ctx, "channel_delete", "Mass channel deletion"):
            return

        name = target.name
        await target.delete(reason=f"Deleted by {ctx.author}")
        if target.id != ctx.channel.id:
            await ctx.send(f"Deleted #{name}.")

    @channel.command(name="rename", aliases=["crn"])
    async def channel_rename(self, ctx, target: discord.TextChannel, *, new_name: str):
        """Rename a channel."""
        if not await self._check(ctx):
            return
        old_name = target.name
        await target.edit(name=new_name, reason=f"Renamed by {ctx.author}")
        await ctx.send(f"Renamed #{old_name} to #{new_name}.")

    @channel.command(name="lock")
    async def channel_lock(self, ctx, target: discord.TextChannel = None):
        """Lock a channel — @everyone can't send messages."""
        if not await self._check(ctx):
            return
        target = target or ctx.channel
        overwrite = target.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await target.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Locked by {ctx.author}")
        await ctx.send(f"🔒 Locked {target.mention}.")

    @channel.command(name="unlock")
    async def channel_unlock(self, ctx, target: discord.TextChannel = None):
        """Unlock a channel — restores @everyone's ability to send messages."""
        if not await self._check(ctx):
            return
        target = target or ctx.channel
        overwrite = target.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await target.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Unlocked by {ctx.author}")
        await ctx.send(f"🔓 Unlocked {target.mention}.")

    @channel.command(name="slowmode", aliases=["slow"])
    async def channel_slowmode(self, ctx, seconds: int, target: discord.TextChannel = None):
        """Set slowmode delay in seconds (0 to disable). Example: ~channel slowmode 10"""
        if not await self._check(ctx):
            return
        if seconds < 0 or seconds > 21600:
            await ctx.send("Slowmode must be between 0 and 21600 seconds (6 hours).")
            return
        target = target or ctx.channel
        await target.edit(slowmode_delay=seconds, reason=f"Slowmode set by {ctx.author}")
        if seconds == 0:
            await ctx.send(f"Slowmode disabled in {target.mention}.")
        else:
            await ctx.send(f"Slowmode set to {seconds}s in {target.mention}.")

    @channel.command(name="category", aliases=["ccat"])
    async def channel_category(self, ctx, target: discord.TextChannel, *, category_name: str):
        """Move a channel into a category."""
        if not await self._check(ctx):
            return
        cat_obj = discord.utils.find(lambda c: c.name.lower() == category_name.lower(), ctx.guild.categories)
        if cat_obj is None:
            await ctx.send(f"Couldn't find category `{category_name}`.")
            return
        await target.edit(category=cat_obj, reason=f"Moved by {ctx.author}")
        await ctx.send(f"Moved {target.mention} into `{cat_obj.name}`.")

    @channel.command(name="perms", aliases=["cperms"])
    async def channel_perms(self, ctx, target: discord.TextChannel, entity: discord.Member | discord.Role, action: str, perm: str):
        """Set a permission override. Example: ~channel perms #general @Muted deny send"""
        if not await self._check(ctx):
            return

        action = action.lower()
        if action not in ("allow", "deny", "reset"):
            await ctx.send("Action must be `allow`, `deny`, or `reset`.")
            return

        perm_attr = PERM_ALIASES.get(perm.lower(), perm.lower())
        overwrite = target.overwrites_for(entity)
        if not hasattr(overwrite, perm_attr):
            await ctx.send(f"Unknown permission `{perm}`.")
            return

        value = True if action == "allow" else (False if action == "deny" else None)
        setattr(overwrite, perm_attr, value)

        try:
            await target.set_permissions(entity, overwrite=overwrite, reason=f"Perms edited by {ctx.author}")
        except discord.Forbidden:
            await ctx.send("Couldn't update — check the bot's role is above this role/user's highest role.")
            return

        await ctx.send(f"Set `{perm_attr}` to `{action}` for {entity.mention} in {target.mention}.")

    @channel.command(name="nuke")
    async def channel_nuke(self, ctx, target: discord.TextChannel = None):
        """Deletes a channel and recreates an identical copy in the same position. Requires antinuke admin+ and confirmation."""
        if not await self._antinuke_check(ctx):
            return

        target = target or ctx.channel
        if not await ask_confirm(ctx, f"💥 Nuke {target.mention}? This deletes and recreates it — all message history is lost."):
            await ctx.send("Cancelled.")
            return

        position = target.position
        clone = await target.clone(reason=f"Nuked by {ctx.author}")
        await target.delete(reason=f"Nuked by {ctx.author}")
        await clone.edit(position=position)
        await clone.send(f"💥 This channel was nuked by {ctx.author.mention}.")

    @channel.command(name="copy", aliases=["duplicate"])
    async def channel_copy(self, ctx, target: discord.TextChannel = None):
        """Duplicates a channel (same settings/permissions) without deleting the original. Requires antinuke admin+."""
        if not await self._antinuke_check(ctx):
            return
        target = target or ctx.channel
        clone = await target.clone(reason=f"Copied by {ctx.author}")
        await ctx.send(f"Created a copy: {clone.mention}")

    # === Standalone flat shortcuts (no ~channel prefix needed) ===

    @commands.command(name="cc")
    async def cc_flat(self, ctx, name: str, *, category: str = None):
        """Shortcut for ~channel create."""
        await self.channel_create.callback(self, ctx, name, category=category)

    @commands.command(name="cd")
    async def cd_flat(self, ctx, target: discord.TextChannel = None):
        """Shortcut for ~channel delete."""
        await self.channel_delete.callback(self, ctx, target)

    @commands.command(name="crn")
    async def crn_flat(self, ctx, target: discord.TextChannel, *, new_name: str):
        """Shortcut for ~channel rename."""
        await self.channel_rename.callback(self, ctx, target, new_name=new_name)

    @commands.command(name="lock")
    async def lock_flat(self, ctx, target: discord.TextChannel = None):
        """Shortcut for ~channel lock."""
        await self.channel_lock.callback(self, ctx, target)

    @commands.command(name="unlock")
    async def unlock_flat(self, ctx, target: discord.TextChannel = None):
        """Shortcut for ~channel unlock."""
        await self.channel_unlock.callback(self, ctx, target)

    @commands.command(name="slow")
    async def slow_flat(self, ctx, seconds: int, target: discord.TextChannel = None):
        """Shortcut for ~channel slowmode."""
        await self.channel_slowmode.callback(self, ctx, seconds, target)

    @commands.command(name="ccat")
    async def ccat_flat(self, ctx, target: discord.TextChannel, *, category_name: str):
        """Shortcut for ~channel category."""
        await self.channel_category.callback(self, ctx, target, category_name=category_name)

    @commands.command(name="cperms")
    async def cperms_flat(self, ctx, target: discord.TextChannel, entity: discord.Member | discord.Role, action: str, perm: str):
        """Shortcut for ~channel perms."""
        await self.channel_perms.callback(self, ctx, target, entity, action, perm)

    @commands.command(name="nuke")
    async def nuke_flat(self, ctx, target: discord.TextChannel = None):
        """Shortcut for ~channel nuke."""
        await self.channel_nuke.callback(self, ctx, target)

    @commands.command(name="copy")
    async def copy_flat(self, ctx, target: discord.TextChannel = None):
        """Shortcut for ~channel copy."""
        await self.channel_copy.callback(self, ctx, target)

async def setup(bot):
    await bot.add_cog(Channels(bot))
