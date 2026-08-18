import discord
from discord.ext import commands
from config.owner import Me

class UnbanCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return ctx.author.id in Me or await self.bot.is_owner(ctx.author)

    @commands.command(name="forceunban")
    async def force_unban_direct(self, ctx, user_id: int = None):
        """Forcefully searches all ban lists across servers and unbans your exact ID."""
        target_id = user_id if user_id else ctx.author.id
        await ctx.send(f"⚙️ Target User ID: `{target_id}`. Fetching ban records across {len(self.bot.guilds)} servers...")

        unbanned_servers = []

        for guild in self.bot.guilds:
            if not guild.me.guild_permissions.ban_members:
                await ctx.send(f"⚠️ Skipped **{guild.name}**: Bot missing `Ban Members` permission.")
                continue

            try:
                # Iterate through the server's actual ban list to find your exact user object
                ban_entry = None
                async for ban in guild.bans():
                    if ban.user.id == target_id:
                        ban_entry = ban
                        break

                if ban_entry:
                    # Execute direct unban request
                    await guild.unban(ban_entry.user, reason="Direct forced API unban")
                    unbanned_servers.append(guild)
                    await ctx.send(f"✅ Successfully removed ban for `{ban_entry.user}` in **{guild.name}**!")
                else:
                    await ctx.send(f"ℹ️ User ID `{target_id}` was not found on the ban list for **{guild.name}**.")

            except discord.Forbidden:
                await ctx.send(f"❌ Failed in **{guild.name}**: Hierarchy error (Bot role is below the ban).")
            except Exception as e:
                await ctx.send(f"❌ Error scanning **{guild.name}**: {e}")

        if not unbanned_servers:
            return await ctx.send("❓ If you still cannot join, the bot is either not in that server, or lacks admin/ban permissions.")

        # Generate fresh invite link for successfully unbanned servers
        for guild in unbanned_servers:
            invite_url = None
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).create_instant_invite:
                    try:
                        invite = await channel.create_invite(max_uses=1, max_age=86400, reason="Unban rejoin link")
                        invite_url = invite.url
                        break
                    except Exception:
                        continue

            if invite_url:
                await ctx.send(f"🔗 Fresh invite link for **{guild.name}**: {invite_url}")
            else:
                await ctx.send(f"⚠️ Unbanned from **{guild.name}**, but missing `Create Invite` permissions in channels.")

async def setup(bot):
    await bot.add_cog(UnbanCog(bot))
