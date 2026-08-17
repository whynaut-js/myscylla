import discord
from discord.ext import commands
from utils import antinuke as an
from utils.confirm import ask_confirm  # Assumes ask_confirm is in utils/confirm.py or import accordingly

def wipe_permission_check():
    async def predicate(ctx):
        if not ctx.guild:
            return False
        # Check if Bot Owner
        if await ctx.bot.is_owner(ctx.author):
            return True
        # Check if Server Owner
        if ctx.author.id == ctx.guild.owner_id:
            return True
        # Check if Antinuke Owner
        if await an.is_antinuke_owner(ctx.bot, ctx.guild, ctx.author):
            return True
        return False
    return commands.check(predicate)

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
            "`~wipe channels <name>` (Alias: `~wc`) — Mass delete matching channels\n"
            "`~wipe roles <name>` (Alias: `~wr`) — Mass delete matching roles\n"
            "`~wipe bots <name>` (Alias: `~wb`) — Mass ban matching bots\n"
            "`~wipe all <name>` — Mass delete channels, roles, and ban bots all at once"
        )

    @wipe.command(name="channels", aliases=["channel", "ch", "wc"])
    @wipe_permission_check()
    async def wipe_channels(self, ctx, *, name: str):
        """Mass delete channels matching a specific name."""
        confirmed = await ask_confirm(ctx, f"⚠️ Are you sure you want to mass-delete channels matching **`{name}`**?")
        if not confirmed:
            return await ctx.send("Wipe channels cancelled.", delete_after=5)

        clean_name = name.strip().lower().replace(" ", "-")
        raw_name = name.strip().lower()
        status_msg = await ctx.send(f"⏳ **Deleting channels matching:** `{name}`...")
        
        channels_deleted = 0
        for channel in list(ctx.guild.channels):
            if channel.id == ctx.channel.id:
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
        """Mass delete roles matching a specific name."""
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
        """Mass delete channels, roles, and ban bots matching a specific name."""
        confirmed = await ask_confirm(ctx, f"🚨 **DANGER:** Are you sure you want to completely wipe channels, roles, AND ban bots matching **`{name}`**?")
        if not confirmed:
            return await ctx.send("Full wipe cancelled.", delete_after=5)

        clean_name = name.strip().lower().replace(" ", "-")
        raw_name = name.strip().lower()
        status_msg = await ctx.send(f"⏳ **Starting full wipe for:** `{name}`...")

        channels_deleted = 0
        roles_deleted = 0
        bots_banned = 0

        for channel in list(ctx.guild.channels):
            if channel.id == ctx.channel.id:
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
        embed.add_field(name="Roles Deleted", value=str(roles_deleted), inline=True)
        embed.add_field(name="Bots Banned", value=str(bots_banned), inline=True)

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

async def setup(bot):
    await bot.add_cog(Wipe(bot))
