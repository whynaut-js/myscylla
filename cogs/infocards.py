import discord
from discord.ext import commands

class InfoCards(commands.Cog):
    """Server and user info, icons, and banners."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="serverinfo", aliases=["si"])
    async def serverinfo(self, ctx):
        """Shows info about this server."""
        guild = ctx.guild
        embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier} ({guild.premium_subscription_count} boosts)", inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, style="R"), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="usericon", aliases=["avatar", "av"])
    async def usericon(self, ctx, member: discord.Member = None):
        """Shows a user's avatar (yours if no one is mentioned)."""
        member = member or ctx.author
        embed = discord.Embed(title=f"{member.display_name}'s avatar", color=discord.Color.blurple())
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="userbanner", aliases=["banner"])
    async def userbanner(self, ctx, member: discord.Member = None):
        """Shows a user's profile banner (yours if no one is mentioned)."""
        member = member or ctx.author
        user = await self.bot.fetch_user(member.id)
        if not user.banner:
            await ctx.send(f"{member.display_name} doesn't have a banner set.")
            return
        embed = discord.Embed(title=f"{member.display_name}'s banner", color=discord.Color.blurple())
        embed.set_image(url=user.banner.url)
        await ctx.send(embed=embed)

    @commands.command(name="servericon", aliases=["sicon"])
    async def servericon(self, ctx):
        """Shows this server's icon."""
        if not ctx.guild.icon:
            await ctx.send("This server doesn't have an icon set.")
            return
        embed = discord.Embed(title=f"{ctx.guild.name}'s icon", color=discord.Color.blurple())
        embed.set_image(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)

    @commands.command(name="serverbanner", aliases=["sbanner"])
    async def serverbanner(self, ctx):
        """Shows this server's banner."""
        if not ctx.guild.banner:
            await ctx.send("This server doesn't have a banner set.")
            return
        embed = discord.Embed(title=f"{ctx.guild.name}'s banner", color=discord.Color.blurple())
        embed.set_image(url=ctx.guild.banner.url)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(InfoCards(bot))
