import discord
from discord.ext import commands
from utils import antinuke as an

class Antinuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        executor = await an.get_executor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        if executor:
            await an.track_channel_creation(channel.guild.id, executor.id, channel.id)
            await an.handle_detected(
                self.bot,
                channel.guild,
                executor,
                "channel_create",
                f"Mass channel creation (created #{channel.name})",
                target_obj=channel
            )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        executor = await an.get_executor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        if executor:
            ch_info = {
                "name": channel.name,
                "type": channel.type,
                "category_id": channel.category_id,
            }
            # Record this deletion immediately — if a LATER deletion in the same
            # window crosses the threshold, this one still gets rolled back too.
            await an.track_event(channel.guild.id, executor.id, "channel_delete", ch_info)
            await an.handle_detected(
                self.bot,
                channel.guild,
                executor,
                "channel_delete",
                f"Mass channel deletion (deleted #{channel.name})",
                target_obj=ch_info
            )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        executor = await an.get_executor(role.guild, discord.AuditLogAction.role_delete, role.id)
        if executor:
            role_info = {
                "name": role.name,
                "permissions": role.permissions.value,
                "color": role.color.value,
                "hoist": role.hoist,
                "mentionable": role.mentionable
            }
            await an.track_event(role.guild.id, executor.id, "role_delete", role_info)
            await an.handle_detected(
                self.bot,
                role.guild,
                executor,
                "role_delete",
                f"Mass role deletion (deleted @{role.name})",
                target_obj=role_info
            )

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        executor = await an.get_executor(guild, discord.AuditLogAction.ban, user.id)
        if executor:
            await an.handle_detected(self.bot, guild, executor, "ban", f"Mass user banning (banned {user})")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        guild = member.guild
        executor = await an.get_executor(guild, discord.AuditLogAction.kick, member.id)
        if executor:
            await an.handle_detected(self.bot, guild, executor, "kick", f"Mass user kicking (kicked {member})")

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        if message.mention_everyone:
            config = await an.get_config(self.bot, message.guild.id)
            if not config["enabled"]:
                return
            if await an.is_whitelisted(self.bot, message.guild, message.author):
                return
            try:
                await message.delete()
            except Exception:
                pass
            await an.strip_everyone_perm(message.guild, message.author)
            await an.handle_detected(
                self.bot,
                message.guild,
                message.author,
                "everyone_ping",
                f"Mass @everyone/@here ping in {message.channel.mention}"
            )

async def setup(bot):
    await bot.add_cog(Antinuke(bot))
