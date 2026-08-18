import discord
from discord.ext import commands

class UserInfo(commands.Cog):
    """View a member's roles and a general profile overview."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="memberroles", aliases=["mroles"])
    async def memberroles(self, ctx, member: discord.Member = None):
        """List every role a member has. Example: ~memberroles @user"""
        member = member or ctx.author
        roles = [r for r in member.roles if not r.is_default()]
        if not roles:
            await ctx.send(f"{member.mention} has no roles.", allowed_mentions=discord.AllowedMentions.none())
            return
        roles.sort(key=lambda r: r.position, reverse=True)
        role_list = ", ".join(r.mention for r in roles)
        embed = discord.Embed(
            title=f"{member.display_name}'s roles ({len(roles)})",
            description=role_list,
            color=member.color if member.color.value else discord.Color.blurple(),
        )
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="overview", aliases=["ov"])
    async def overview(self, ctx, member: discord.Member = None):
        """View a member's profile: join date, account age, roles, and who invited them."""
        member = member or ctx.author

        row = await self.bot.db.fetchone(
            "SELECT inviter_id, invite_code FROM join_invites WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, member.id),
        )
        if row and row[0]:
            inviter = ctx.guild.get_member(row[0])
            invited_by = inviter.mention if inviter else f"<@{row[0]}>"
            invite_text = f"{invited_by} (`{row[1]}`)" if row[1] else invited_by
        elif row and row[1]:
            invite_text = f"Vanity link `{row[1]}`"
        else:
            invite_text = "Unknown (joined before tracking started, or couldn't be determined)"

        roles = [r for r in member.roles if not r.is_default()]
        roles.sort(key=lambda r: r.position, reverse=True)
        role_text = ", ".join(r.mention for r in roles[:10]) if roles else "None"
        if len(roles) > 10:
            role_text += f" (+{len(roles) - 10} more)"

        embed = discord.Embed(
            title=f"Overview — {member}",
            color=member.color if member.color.value else discord.Color.blurple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Account created", value=discord.utils.format_dt(member.created_at, style="R"), inline=True)
        embed.add_field(name="Joined server", value=discord.utils.format_dt(member.joined_at, style="R") if member.joined_at else "Unknown", inline=True)
        embed.add_field(name="Invited by", value=invite_text, inline=False)
        embed.add_field(name=f"Roles ({len(roles)})", value=role_text, inline=False)

        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

async def setup(bot):
    await bot.add_cog(UserInfo(bot))
