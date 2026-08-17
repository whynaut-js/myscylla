import discord
from discord.ext import commands
from utils.permissions import has_botperm

class Nicknames(commands.Cog):
    """Change or freeze a member's nickname."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="nick")
    async def nick(self, ctx, member: discord.Member, *, new_nick: str = None):
        """Change a member's nickname. Leave blank to reset it. Example: ~nick @user CoolName"""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "manage_roles"):
            await ctx.send("You don't have permission to change nicknames.")
            return
        try:
            await member.edit(nick=new_nick, reason=f"Nickname changed by {ctx.author}")
        except discord.Forbidden:
            await ctx.send("I can't change that member's nickname (role hierarchy, or they're the server owner).")
            return
        if new_nick:
            await ctx.send(f"Changed {member.mention}'s nickname to `{new_nick}`.")
        else:
            await ctx.send(f"Reset {member.mention}'s nickname.")

    @commands.command(name="forcenick", aliases=["fn"])
    async def forcenick(self, ctx, member: discord.Member, *, new_nick: str):
        """Set and FREEZE a member's nickname — they can't change it themselves. Example: ~forcenick @user Frozen"""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "manage_roles"):
            await ctx.send("You don't have permission to force nicknames.")
            return
        try:
            await member.edit(nick=new_nick, reason=f"Nickname frozen by {ctx.author}")
        except discord.Forbidden:
            await ctx.send("I can't change that member's nickname (role hierarchy, or they're the server owner).")
            return
        await self.bot.db.execute(
            """
            INSERT INTO forced_nicknames (guild_id, user_id, nickname) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET nickname = excluded.nickname
            """,
            (ctx.guild.id, member.id, new_nick),
        )
        await ctx.send(f"Froze {member.mention}'s nickname to `{new_nick}`. They can't change it until unforced.")

    @commands.command(name="unforcenick", aliases=["ufn"])
    async def unforcenick(self, ctx, member: discord.Member):
        """Remove a nickname freeze — they can change their own nickname again."""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "manage_roles"):
            await ctx.send("You don't have permission to unforce nicknames.")
            return
        await self.bot.db.execute(
            "DELETE FROM forced_nicknames WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, member.id),
        )
        await ctx.send(f"Unfroze {member.mention}'s nickname.")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick == after.nick:
            return
        row = await self.bot.db.fetchone(
            "SELECT nickname FROM forced_nicknames WHERE guild_id = ? AND user_id = ?",
            (after.guild.id, after.id),
        )
        if row is None:
            return
        locked_nick = row[0]
        if after.nick != locked_nick:
            try:
                await after.edit(nick=locked_nick, reason="Nickname is frozen")
            except discord.Forbidden:
                pass

async def setup(bot):
    await bot.add_cog(Nicknames(bot))
