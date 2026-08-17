import discord
from discord.ext import commands
from utils.checks import is_server_owner

class ModLog(commands.Cog):
    """View and configure the moderation case history."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="modsetup", aliases=["ms"])
    @is_server_owner()
    async def modsetup(self, ctx):
        """One-time setup: creates the mod-logs channel."""
        row = await self.bot.db.fetchone(
            "SELECT modlog_channel_id FROM guild_config WHERE guild_id = ?", (ctx.guild.id,)
        )
        if row and row[0] and ctx.guild.get_channel(row[0]):
            await ctx.send("Mod-log channel is already set up.")
            return

        channel = await ctx.guild.create_text_channel(
            "mod-logs",
            overwrites={ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)},
            reason="Mod log setup",
        )

        await self.bot.db.execute(
            """
            INSERT INTO guild_config (guild_id, modlog_channel_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET modlog_channel_id = excluded.modlog_channel_id
            """,
            (ctx.guild.id, channel.id),
        )
        await ctx.send(
            f"Mod-log channel created: {channel.mention}. "
            f"It's hidden from everyone by default — grant your staff roles access manually."
        )

    @commands.command(name="modreport", aliases=["mr"])
    async def modreport(self, ctx, target: discord.Member):
        """View all moderation actions taken against a user."""
        rows = await self.bot.db.fetchall(
            "SELECT action, COUNT(*) FROM mod_cases WHERE guild_id = ? AND target_id = ? GROUP BY action",
            (ctx.guild.id, target.id),
        )
        if not rows:
            await ctx.send(f"{target.mention} has no moderation history.")
            return

        counts = "\n".join(f"`{action}`: {count}" for action, count in rows)
        total = sum(count for _, count in rows)

        recent = await self.bot.db.fetchall(
            "SELECT case_id, action FROM mod_cases WHERE guild_id = ? AND target_id = ? ORDER BY case_id DESC LIMIT 5",
            (ctx.guild.id, target.id),
        )
        recent_text = ", ".join(f"#{cid} ({action})" for cid, action in recent)

        await ctx.send(
            f"**Moderation report for {target.mention}** (total: {total})\n{counts}\n\n"
            f"Recent cases: {recent_text}\nUse `~modcase <id>` for full details."
        )

    @commands.command(name="modhistory", aliases=["mh"])
    async def modhistory(self, ctx, moderator: discord.Member):
        """View all moderation actions taken by a moderator."""
        rows = await self.bot.db.fetchall(
            "SELECT action, COUNT(*) FROM mod_cases WHERE guild_id = ? AND moderator_id = ? GROUP BY action",
            (ctx.guild.id, moderator.id),
        )
        if not rows:
            await ctx.send(f"{moderator.mention} hasn't taken any moderation actions.")
            return

        counts = "\n".join(f"`{action}`: {count}" for action, count in rows)
        total = sum(count for _, count in rows)

        recent = await self.bot.db.fetchall(
            "SELECT case_id, action FROM mod_cases WHERE guild_id = ? AND moderator_id = ? ORDER BY case_id DESC LIMIT 5",
            (ctx.guild.id, moderator.id),
        )
        recent_text = ", ".join(f"#{cid} ({action})" for cid, action in recent)

        await ctx.send(
            f"**Moderation history for {moderator.mention}** (total actions: {total})\n{counts}\n\n"
            f"Recent cases: {recent_text}\nUse `~modcase <id>` for full details."
        )

    @commands.command(name="modcase", aliases=["mc"])
    async def modcase(self, ctx, case_id: int):
        """View full details of a specific moderation case."""
        row = await self.bot.db.fetchone(
            "SELECT action, moderator_id, target_id, reason, timestamp FROM mod_cases WHERE guild_id = ? AND case_id = ?",
            (ctx.guild.id, case_id),
        )
        if row is None:
            await ctx.send(f"No case #{case_id} found.")
            return

        action, moderator_id, target_id, reason, timestamp = row
        moderator = ctx.guild.get_member(moderator_id)
        target = ctx.guild.get_member(target_id)

        embed = discord.Embed(title=f"Case #{case_id} — {action.capitalize()}", color=discord.Color.orange())
        embed.add_field(name="Target", value=target.mention if target else f"Unknown ({target_id})", inline=False)
        embed.add_field(name="Moderator", value=moderator.mention if moderator else f"Unknown ({moderator_id})", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="When", value=timestamp, inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ModLog(bot))
