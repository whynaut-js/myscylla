import discord
from discord.ext import commands, tasks
from utils import antinuke as an

class Antinuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_loop.start()

    def cog_unload(self):
        self.cleanup_loop.cancel()

    @tasks.loop(minutes=10)
    async def cleanup_loop(self):
        # FIX #4: periodic memory cleanup so trackers don't grow forever
        await an.cleanup_stale_entries()

    @cleanup_loop.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

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
            overwrites_data = []
            for target, overwrite in channel.overwrites.items():
                allow, deny = overwrite.pair()
                overwrites_data.append({
                    "target_id": target.id,
                    "target_type": "role" if isinstance(target, discord.Role) else "member",
                    "allow": allow.value,
                    "deny": deny.value,
                })

            ch_info = {
                "name": channel.name,
                "type": channel.type,
                "category_id": channel.category_id,
                "position": channel.position,
                "topic": getattr(channel, "topic", None),
                "slowmode_delay": getattr(channel, "slowmode_delay", 0),
                "nsfw": getattr(channel, "nsfw", False),
                "overwrites": overwrites_data,
            }
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
                "mentionable": role.mentionable,
                "position": role.position,
                "member_ids": [m.id for m in role.members],
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
    async def on_webhooks_update(self, channel):
        # FIX #3: this listener didn't exist at all before — webhook_create
        # had a configurable threshold that nothing ever checked.
        executor = await an.get_executor(channel.guild, discord.AuditLogAction.webhook_create)
        if executor:
            await an.handle_detected(
                self.bot,
                channel.guild,
                executor,
                "webhook_create",
                f"Webhook creation spam (in #{channel.name})"
            )

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # FIX #7 (restored): unauthorized bot added → instant kick, no
        # threshold — a single unwanted bot invite is never legitimate.
        if not member.bot:
            return
        executor = await an.get_executor(member.guild, discord.AuditLogAction.bot_add, member.id)
        if not executor:
            return
        if await an.is_whitelisted(self.bot, member.guild, executor):
            return
        config = await an.get_config(self.bot, member.guild.id)
        if not config["enabled"]:
            return
        try:
            await member.kick(reason="Antinuke: unauthorized bot addition")
        except discord.Forbidden:
            pass
        await an.handle_detected_instant(self.bot, member.guild, executor, f"Added unauthorized bot ({member})")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        # FIX #7 (restored): someone grants Administrator to a role → revert
        # instantly and punish, no threshold — this is never accidental.
        if before.permissions.administrator or not after.permissions.administrator:
            return
        executor = await an.get_executor(after.guild, discord.AuditLogAction.role_update, after.id)
        if not executor:
            return
        if await an.is_whitelisted(self.bot, after.guild, executor):
            return
        config = await an.get_config(self.bot, after.guild.id)
        if not config["enabled"]:
            return
        try:
            await after.edit(permissions=before.permissions, reason="Antinuke: reverted unauthorized admin grant")
        except discord.Forbidden:
            pass
        await an.handle_detected_instant(self.bot, after.guild, executor, f"Granted Administrator to @{after.name}")

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
