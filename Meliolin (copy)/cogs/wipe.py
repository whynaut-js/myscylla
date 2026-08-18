import re
import discord
from discord.ext import commands
from utils import antinuke as an
from utils.confirm import ask_confirm

def wipe_permission_check():
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.author.id == ctx.guild.owner_id:
            return True
        if await an.is_antinuke_owner(ctx.bot, ctx.guild, ctx.author):
            return True
        return False
    return commands.check(predicate)

def _resolve_query(ctx, query: str) -> str:
    """If the query is a raw ID (channel, role, or category), look up its
    actual name and use THAT as the match pattern instead. Falls back to
    treating the query as literal text if it's not a valid ID."""
    query = query.strip()
    if not query.isdigit():
        return query

    obj_id = int(query)
    channel = ctx.guild.get_channel(obj_id)
    if channel:
        return channel.name
    role = ctx.guild.get_role(obj_id)
    if role:
        return role.name
    return query

class Wipe(commands.Cog):
    """Emergency server cleanup and wipe tools."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="wipe", invoke_without_command=True)
    @wipe_permission_check()
    async def wipe(self, ctx):
        """Emergency wipe group command."""
        await ctx.send(
            "**🧹 Emergency Wipe Commands:**\n"
            "`~wipe channels <name/id>` (`~wc`) — Mass delete matching channels\n"
            "`~wipe roles <name/id>` (`~wr`) — Mass delete matching roles\n"
            "`~wipe categories <name/id>` (`~wcat`) — Mass delete matching categories (and everything in them)\n"
            "`~wipe bots <name>` (`~wb`) — Mass ban matching bots\n"
            "`~wipe all <name/id>` (`~wall`) — Mass delete channels, roles, categories, and ban bots all at once\n"
            "`~wipe nuked` (`~wn`) — Auto-detects and deletes nuke-pattern spam (e.g. `nuke 1`, `nuke 2`, `nuke 3`...) with NO name needed\n\n"
            "Tip: pass a channel/role ID instead of a name — it'll look up the real name and match against that."
        )

    @wipe.command(name="channels", aliases=["channel", "ch", "wc"])
    @wipe_permission_check()
    async def wipe_channels(self, ctx, *, name: str):
        """Mass delete channels matching a specific name or ID."""
        name = _resolve_query(ctx, name)
        confirmed = await ask_confirm(ctx, f"⚠️ Are you sure you want to mass-delete channels matching **`{name}`**?")
        if not confirmed:
            return await ctx.send("Wipe channels cancelled.", delete_after=5)

        clean_name = name.strip().lower().replace(" ", "-")
        raw_name = name.strip().lower()
        status_msg = await ctx.send(f"⏳ **Deleting channels matching:** `{name}`...")

        channels_deleted = 0
        for channel in list(ctx.guild.channels):
            if channel.id == ctx.channel.id or isinstance(channel, discord.CategoryChannel):
                continue
            if clean_name in channel.name.lower() or raw_name in channel.name.lower():
                try:
                    await channel.delete(reason=f"Wipe Channels by {ctx.author}")
                    channels_deleted += 1
                except Exception:
                    pass

        embed = discord.Embed(title="🧹 Channel Wipe Complete", color=discord.Color.green())
        embed.add_field(name="Target Query", value=f"`{name}`", inline=False)
        embed.add_field(name="Channels Deleted", value=str(channels_deleted), inline=True)

        try:
            await status_msg.edit(content=None, embed=embed)
        except Exception:
            await ctx.send(embed=embed)

    @wipe.command(name="roles", aliases=["role", "wr"])
    @wipe_permission_check()
    async def wipe_roles(self, ctx, *, name: str):
        """Mass delete roles matching a specific name or ID."""
        name = _resolve_query(ctx, name)
        confirmed = await ask_confirm(ctx, f"⚠️ Are you sure you want to mass-delete roles matching **`{name}`**?")
        if not confirmed:
            return await ctx.send("Wipe roles cancelled.", delete_after=5)

        raw_name = name.strip().lower()
        status_msg = await ctx.send(f"⏳ **Deleting roles matching:** `{name}`...")

        roles_deleted = 0
        for role in list(ctx.guild.roles):
            if role.is_default() or role.managed or role >= ctx.guild.me.top_role:
                continue
            if raw_name in role.name.lower():
                try:
                    await role.delete(reason=f"Wipe Roles by {ctx.author}")
                    roles_deleted += 1
                except Exception:
                    pass

        embed = discord.Embed(title="🧹 Role Wipe Complete", color=discord.Color.green())
        embed.add_field(name="Target Query", value=f"`{name}`", inline=False)
        embed.add_field(name="Roles Deleted", value=str(roles_deleted), inline=True)

        try:
            await status_msg.edit(content=None, embed=embed)
        except Exception:
            await ctx.send(embed=embed)

    @wipe.command(name="categories", aliases=["category", "cat", "wcat"])
    @wipe_permission_check()
    async def wipe_categories(self, ctx, *, name: str):
        """Mass delete categories matching a name/ID — deletes the channels inside them too."""
        name = _resolve_query(ctx, name)
        confirmed = await ask_confirm(ctx, f"⚠️ Delete categories matching **`{name}`** AND everything inside them?")
        if not confirmed:
            return await ctx.send("Wipe categories cancelled.", delete_after=5)

        raw_name = name.strip().lower()
        status_msg = await ctx.send(f"⏳ **Deleting categories matching:** `{name}`...")

        cats_deleted = 0
        channels_deleted = 0
        for category in list(ctx.guild.categories):
            if raw_name in category.name.lower():
                for channel in list(category.channels):
                    if channel.id == ctx.channel.id:
                        continue
                    try:
                        await channel.delete(reason=f"Wipe Categories by {ctx.author}")
                        channels_deleted += 1
                    except Exception:
                        pass
                try:
                    await category.delete(reason=f"Wipe Categories by {ctx.author}")
                    cats_deleted += 1
                except Exception:
                    pass

        embed = discord.Embed(title="🧹 Category Wipe Complete", color=discord.Color.green())
        embed.add_field(name="Target Query", value=f"`{name}`", inline=False)
        embed.add_field(name="Categories Deleted", value=str(cats_deleted), inline=True)
        embed.add_field(name="Channels Deleted", value=str(channels_deleted), inline=True)

        try:
            await status_msg.edit(content=None, embed=embed)
        except Exception:
            await ctx.send(embed=embed)

    @wipe.command(name="bots", aliases=["bot", "wb"])
    @wipe_permission_check()
    async def wipe_bots(self, ctx, *, name: str):
        """Mass ban bots matching a specific name."""
        confirmed = await ask_confirm(ctx, f"⚠️ Are you sure you want to mass-ban bots matching **`{name}`**?")
        if not confirmed:
            return await ctx.send("Wipe bots cancelled.", delete_after=5)

        raw_name = name.strip().lower()
        status_msg = await ctx.send(f"⏳ **Banning bots matching:** `{name}`...")

        bots_banned = 0
        for member in list(ctx.guild.members):
            if member.bot and member.id != self.bot.user.id:
                if raw_name in member.name.lower() or raw_name in member.display_name.lower():
                    if member.top_role < ctx.guild.me.top_role:
                        try:
                            await ctx.guild.ban(member, reason=f"Wipe Bots by {ctx.author}")
                            bots_banned += 1
                        except Exception:
                            pass

        embed = discord.Embed(title="🧹 Bot Wipe Complete", color=discord.Color.green())
        embed.add_field(name="Target Query", value=f"`{name}`", inline=False)
        embed.add_field(name="Bots Banned", value=str(bots_banned), inline=True)

        try:
            await status_msg.edit(content=None, embed=embed)
        except Exception:
            await ctx.send(embed=embed)

    @wipe.command(name="all")
    @wipe_permission_check()
    async def wipe_all(self, ctx, *, name: str):
        """Mass delete channels, roles, categories, and ban bots matching a name/ID."""
        name = _resolve_query(ctx, name)
        confirmed = await ask_confirm(ctx, f"🚨 **DANGER:** Fully wipe everything matching **`{name}`** (channels, roles, categories, bots)?")
        if not confirmed:
            return await ctx.send("Full wipe cancelled.", delete_after=5)

        clean_name = name.strip().lower().replace(" ", "-")
        raw_name = name.strip().lower()
        status_msg = await ctx.send(f"⏳ **Starting full wipe for:** `{name}`...")

        channels_deleted = 0
        cats_deleted = 0
        roles_deleted = 0
        bots_banned = 0

        for category in list(ctx.guild.categories):
            if raw_name in category.name.lower():
                for channel in list(category.channels):
                    if channel.id == ctx.channel.id:
                        continue
                    try:
                        await channel.delete(reason=f"Wipe All by {ctx.author}")
                        channels_deleted += 1
                    except Exception:
                        pass
                try:
                    await category.delete(reason=f"Wipe All by {ctx.author}")
                    cats_deleted += 1
                except Exception:
                    pass

        for channel in list(ctx.guild.channels):
            if channel.id == ctx.channel.id or isinstance(channel, discord.CategoryChannel):
                continue
            if clean_name in channel.name.lower() or raw_name in channel.name.lower():
                try:
                    await channel.delete(reason=f"Wipe All by {ctx.author}")
                    channels_deleted += 1
                except Exception:
                    pass

        for role in list(ctx.guild.roles):
            if role.is_default() or role.managed or role >= ctx.guild.me.top_role:
                continue
            if raw_name in role.name.lower():
                try:
                    await role.delete(reason=f"Wipe All by {ctx.author}")
                    roles_deleted += 1
                except Exception:
                    pass

        for member in list(ctx.guild.members):
            if member.bot and member.id != self.bot.user.id:
                if raw_name in member.name.lower() or raw_name in member.display_name.lower():
                    if member.top_role < ctx.guild.me.top_role:
                        try:
                            await ctx.guild.ban(member, reason=f"Wipe All by {ctx.author}")
                            bots_banned += 1
                        except Exception:
                            pass

        embed = discord.Embed(title="🧹 Full Wipe Complete", color=discord.Color.green())
        embed.add_field(name="Target Query", value=f"`{name}`", inline=False)
        embed.add_field(name="Channels Deleted", value=str(channels_deleted), inline=True)
        embed.add_field(name="Categories Deleted", value=str(cats_deleted), inline=True)
        embed.add_field(name="Roles Deleted", value=str(roles_deleted), inline=True)
        embed.add_field(name="Bots Banned", value=str(bots_banned), inline=True)

        try:
            await status_msg.edit(content=None, embed=embed)
        except Exception:
            await ctx.send(embed=embed)

    @wipe.command(name="nuked", aliases=["wn"])
    @wipe_permission_check()
    async def wipe_nuked(self, ctx):
        """Auto-detects nuke-spam patterns (e.g. 'nuke 1', 'new 2', 'x 3'...) —
        channels/roles/categories that share a base name and only differ by a
        trailing number, in groups of 3+. No name needed; scans everything."""
        pattern = re.compile(r"^(.*?)[\s\-_]*(\d+)$")

        def find_groups(items, get_name):
            buckets = {}
            for item in items:
                match = pattern.match(get_name(item).strip().lower())
                if match:
                    base = match.group(1).strip() or "(unnamed)"
                    buckets.setdefault(base, []).append(item)
            return {base: items for base, items in buckets.items() if len(items) >= 3}

        channel_groups = find_groups(
            [c for c in ctx.guild.channels if not isinstance(c, discord.CategoryChannel) and c.id != ctx.channel.id],
            lambda c: c.name
        )
        category_groups = find_groups(ctx.guild.categories, lambda c: c.name)
        role_groups = find_groups(
            [r for r in ctx.guild.roles if not r.is_default() and not r.managed and r < ctx.guild.me.top_role],
            lambda r: r.name
        )

        total_found = sum(len(v) for v in channel_groups.values()) + sum(len(v) for v in category_groups.values()) + sum(len(v) for v in role_groups.values())

        if total_found == 0:
            await ctx.send("No nuke-spam patterns detected (looking for 3+ channels/roles/categories sharing a base name + number, like `nuke 1`, `nuke 2`, `nuke 3`).")
            return

        preview_lines = []
        for base, items in channel_groups.items():
            preview_lines.append(f"**Channels** matching `{base} #`: {len(items)}")
        for base, items in category_groups.items():
            preview_lines.append(f"**Categories** matching `{base} #`: {len(items)}")
        for base, items in role_groups.items():
            preview_lines.append(f"**Roles** matching `{base} #`: {len(items)}")

        confirmed = await ask_confirm(
            ctx,
            "🚨 **Detected likely nuke spam:**\n" + "\n".join(preview_lines) + f"\n\nDelete all {total_found} of these?"
        )
        if not confirmed:
            return await ctx.send("Cancelled.", delete_after=5)

        status_msg = await ctx.send("⏳ Cleaning up detected spam...")
        deleted = 0

        for items in category_groups.values():
            for cat in items:
                for ch in list(cat.channels):
                    try:
                        await ch.delete(reason=f"Wipe Nuked: pattern cleanup by {ctx.author}")
                        deleted += 1
                    except Exception:
                        pass
                try:
                    await cat.delete(reason=f"Wipe Nuked: pattern cleanup by {ctx.author}")
                    deleted += 1
                except Exception:
                    pass

        for items in channel_groups.values():
            for ch in items:
                try:
                    await ch.delete(reason=f"Wipe Nuked: pattern cleanup by {ctx.author}")
                    deleted += 1
                except Exception:
                    pass

        for items in role_groups.values():
            for role in items:
                try:
                    await role.delete(reason=f"Wipe Nuked: pattern cleanup by {ctx.author}")
                    deleted += 1
                except Exception:
                    pass

        embed = discord.Embed(title="🧹 Nuke-Pattern Cleanup Complete", color=discord.Color.green())
        embed.add_field(name="Items Deleted", value=str(deleted), inline=True)
        try:
            await status_msg.edit(content=None, embed=embed)
        except Exception:
            await ctx.send(embed=embed)

    # === Standalone flat shortcuts (no ~wipe prefix needed) ===

    @commands.command(name="wc")
    @wipe_permission_check()
    async def wc_flat(self, ctx, *, name: str):
        """Shortcut for ~wipe channels."""
        await self.wipe_channels.callback(self, ctx, name=name)

    @commands.command(name="wr")
    @wipe_permission_check()
    async def wr_flat(self, ctx, *, name: str):
        """Shortcut for ~wipe roles."""
        await self.wipe_roles.callback(self, ctx, name=name)

    @commands.command(name="wcat")
    @wipe_permission_check()
    async def wcat_flat(self, ctx, *, name: str):
        """Shortcut for ~wipe categories."""
        await self.wipe_categories.callback(self, ctx, name=name)

    @commands.command(name="wb")
    @wipe_permission_check()
    async def wb_flat(self, ctx, *, name: str):
        """Shortcut for ~wipe bots."""
        await self.wipe_bots.callback(self, ctx, name=name)

    @commands.command(name="wall")
    @wipe_permission_check()
    async def wall_flat(self, ctx, *, name: str):
        """Shortcut for ~wipe all."""
        await self.wipe_all.callback(self, ctx, name=name)

    @commands.command(name="wn")
    @wipe_permission_check()
    async def wn_flat(self, ctx):
        """Shortcut for ~wipe nuked."""
        await self.wipe_nuked.callback(self, ctx)

async def setup(bot):
    await bot.add_cog(Wipe(bot))
