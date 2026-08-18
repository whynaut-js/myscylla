import discord
from discord.ext import commands, tasks
from utils import antinuke as an

def antinuke_owner_check():
    async def predicate(ctx):
        if ctx.guild is None:
            return False
        from config.owner import Me
        if ctx.author.id in Me or await ctx.bot.is_owner(ctx.author):
            return True
        return await an.is_antinuke_owner(ctx.bot, ctx.guild, ctx.author)
    return commands.check(predicate)

def antinuke_admin_check():
    async def predicate(ctx):
        if ctx.guild is None:
            return False
        from config.owner import Me
        if ctx.author.id in Me or await ctx.bot.is_owner(ctx.author):
            return True
        return await an.is_antinuke_admin(ctx.bot, ctx.guild, ctx.author)
    return commands.check(predicate)

def server_owner_check():
    async def predicate(ctx):
        if ctx.guild is None:
            return False
        from config.owner import Me
        is_owner = ctx.author.id in Me or await ctx.bot.is_owner(ctx.author)
        return ctx.author.id == ctx.guild.owner_id or is_owner
    return commands.check(predicate)

class Antinuke(commands.Cog):
    """Automatic protection against server nukes."""

    def __init__(self, bot):
        self.bot = bot
        self.cleanup_loop.start()

    def cog_unload(self):
        self.cleanup_loop.cancel()

    @tasks.loop(minutes=10)
    async def cleanup_loop(self):
        await an.cleanup_stale_entries()

    @cleanup_loop.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    # === Event listeners ===

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        executor = await an.get_executor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        if executor:
            await an.track_channel_creation(channel.guild.id, executor.id, channel.id)
            await an.handle_detected(self.bot, channel.guild, executor, "channel_create",
                f"Mass channel creation (created #{channel.name})", target_obj=channel)

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
                    "allow": allow.value, "deny": deny.value,
                })
            ch_info = {
                "name": channel.name, "type": channel.type, "category_id": channel.category_id,
                "position": channel.position, "topic": getattr(channel, "topic", None),
                "slowmode_delay": getattr(channel, "slowmode_delay", 0),
                "nsfw": getattr(channel, "nsfw", False), "overwrites": overwrites_data,
            }
            await an.track_event(channel.guild.id, executor.id, "channel_delete", ch_info)
            await an.handle_detected(self.bot, channel.guild, executor, "channel_delete",
                f"Mass channel deletion (deleted #{channel.name})", target_obj=ch_info)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        executor = await an.get_executor(role.guild, discord.AuditLogAction.role_create, role.id)
        if executor:
            await an.track_role_creation(role.guild.id, executor.id, role.id)
            await an.handle_detected(self.bot, role.guild, executor, "role_create",
                f"Mass role creation (created @{role.name})", target_obj=role)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        executor = await an.get_executor(role.guild, discord.AuditLogAction.role_delete, role.id)
        if executor:
            role_info = {
                "name": role.name, "permissions": role.permissions.value, "color": role.color.value,
                "hoist": role.hoist, "mentionable": role.mentionable, "position": role.position,
                "member_ids": [m.id for m in role.members],
            }
            await an.track_event(role.guild.id, executor.id, "role_delete", role_info)
            await an.handle_detected(self.bot, role.guild, executor, "role_delete",
                f"Mass role deletion (deleted @{role.name})", target_obj=role_info)

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
        executor = await an.get_executor(channel.guild, discord.AuditLogAction.webhook_create)
        if executor:
            await an.handle_detected(self.bot, channel.guild, executor, "webhook_create",
                f"Webhook creation spam (in #{channel.name})")

    @commands.Cog.listener()
    async def on_member_join(self, member):
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
        if not await an.is_whitelisted(self.bot, member.guild, member):
            try:
                await member.kick(reason="Antinuke: unauthorized bot addition")
            except discord.Forbidden:
                pass
            await an.handle_detected_instant(self.bot, member.guild, executor, f"Added unauthorized bot ({member})")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
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
            revert_ok = True
        except discord.Forbidden:
            revert_ok = False

        revert_note = "reverted instantly" if revert_ok else "revert FAILED - check bot's role position"
        await an.handle_detected(self.bot, after.guild, executor, "admin_grant",
            f"Granted Administrator to @{after.name} ({revert_note})")

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
            await an.handle_detected(self.bot, message.guild, message.author, "everyone_ping",
                f"Mass @everyone/@here ping in {message.channel.mention}")

    # === Commands ===

    @commands.group(name="antinuke", aliases=["an"], invoke_without_command=True)
    async def antinuke(self, ctx):
        """Antinuke protection system."""
        await ctx.send(
            "**Antinuke commands:**\n"
            "`~antinuke setup` - one-time setup (server owner only)\n"
            "`~antinuke enable` / `~antinuke disable`\n"
            "`~antinuke status`\n"
            "`~antinuke set <action> <count> <window> [punishment]`\n"
            "  actions: channel_delete, channel_create, role_delete, role_create, admin_grant, ban, kick, webhook_create, everyone_ping\n"
            "`~antinuke punishment <strip/ban/kick>` - default punishment (antinuke owner only)\n"
            "`~antinuke owner add/remove @user` (antinuke owner only)\n"
            "`~antinuke admin add/remove @user` (antinuke owner only)\n"
            "`~antinuke whitelist add/remove @user_or_bot` - whitelisting a BOT requires server owner\n"
            "`~antinuke logchannel #channel`"
        )

    @antinuke.command(name="setup")
    @server_owner_check()
    async def an_setup(self, ctx):
        """One-time setup: enables antinuke, creates the log channel."""
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO antinuke_owners (guild_id, user_id) VALUES (?, ?)", (ctx.guild.id, ctx.guild.owner_id)
        )
        row = await self.bot.db.fetchone("SELECT log_channel_id FROM antinuke_config WHERE guild_id = ?", (ctx.guild.id,))
        log_channel = ctx.guild.get_channel(row[0]) if row and row[0] else None
        if log_channel is None:
            log_channel = await ctx.guild.create_text_channel(
                "antinuke-logs",
                overwrites={ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)},
                reason="Antinuke setup",
            )
        await self.bot.db.execute(
            "INSERT INTO antinuke_config (guild_id, enabled, log_channel_id, punishment) VALUES (?, 1, ?, 'strip') "
            "ON CONFLICT(guild_id) DO UPDATE SET enabled = 1, log_channel_id = excluded.log_channel_id",
            (ctx.guild.id, log_channel.id),
        )
        await ctx.send(f"Antinuke is now **live**. Log channel: {log_channel.mention}.")

    @antinuke.command(name="enable")
    @antinuke_admin_check()
    async def an_enable(self, ctx):
        await an.set_enabled(self.bot, ctx.guild.id, True)
        await ctx.send("Antinuke enabled.")

    @antinuke.command(name="disable")
    @antinuke_admin_check()
    async def an_disable(self, ctx):
        await an.set_enabled(self.bot, ctx.guild.id, False)
        await ctx.send("Antinuke disabled.")

    @antinuke.command(name="status")
    @antinuke_admin_check()
    async def an_status(self, ctx):
        config = await an.get_config(self.bot, ctx.guild.id)
        owners = await self.bot.db.fetchall("SELECT user_id FROM antinuke_owners WHERE guild_id = ?", (ctx.guild.id,))
        admins = await self.bot.db.fetchall("SELECT user_id FROM antinuke_admins WHERE guild_id = ?", (ctx.guild.id,))
        wl = await self.bot.db.fetchall("SELECT user_id FROM antinuke_whitelist WHERE guild_id = ?", (ctx.guild.id,))
        log_channel = ctx.guild.get_channel(config["log_channel_id"]) if config["log_channel_id"] else None
        thresholds_text = "\n".join(
            f"`{k}`: {v['count']}/{v['window']}s" + (f" -> {v['punishment']}" if v.get("punishment") else "")
            for k, v in config["thresholds"].items()
        )
        embed = discord.Embed(title="Antinuke Status", color=discord.Color.blurple())
        embed.add_field(name="Enabled", value="Yes" if config["enabled"] else "No", inline=True)
        embed.add_field(name="Default Punishment", value=config["punishment"], inline=True)
        embed.add_field(name="Log Channel", value=log_channel.mention if log_channel else "Not set", inline=True)
        embed.add_field(name="Owners / Admins / Whitelist", value=f"{len(owners)} / {len(admins)} / {len(wl)}", inline=True)
        embed.add_field(name="Thresholds", value=thresholds_text, inline=False)
        await ctx.send(embed=embed)

    @antinuke.command(name="set")
    @antinuke_owner_check()
    async def an_set(self, ctx, action: str, count: int, window: int, punishment: str = None):
        """Configure one action's threshold/window/punishment. Example: ~antinuke set admin_grant 1 10 ban"""
        if action not in an.DEFAULT_CONFIG:
            await ctx.send(f"Unknown action. Valid: {', '.join(an.DEFAULT_CONFIG.keys())}")
            return
        if count < 1:
            await ctx.send("Count must be at least 1.")
            return
        if punishment and punishment not in ("strip", "ban", "kick"):
            await ctx.send("Punishment must be `strip`, `ban`, or `kick` (or leave blank to use the server default).")
            return
        await an.set_threshold(self.bot, ctx.guild.id, action, count, window, punishment)
        punish_note = f", punishment override: {punishment}" if punishment else ""
        await ctx.send(f"`{action}` set to {count} within {window}s{punish_note}.")

    @antinuke.command(name="punishment")
    @antinuke_owner_check()
    async def an_punishment(self, ctx, punishment: str):
        punishment = punishment.lower()
        if punishment not in ("strip", "ban", "kick"):
            await ctx.send("Punishment must be `strip`, `ban`, or `kick`.")
            return
        await an.set_punishment(self.bot, ctx.guild.id, punishment)
        await ctx.send(f"Default antinuke punishment set to `{punishment}`.")

    @antinuke.group(name="owner", invoke_without_command=True)
    async def an_owner(self, ctx):
        await ctx.send("`~antinuke owner add @user` / `~antinuke owner remove @user`")

    @an_owner.command(name="add")
    @antinuke_owner_check()
    async def an_owner_add(self, ctx, user: discord.Member):
        await self.bot.db.execute("INSERT OR IGNORE INTO antinuke_owners (guild_id, user_id) VALUES (?, ?)", (ctx.guild.id, user.id))
        await ctx.send(f"{user.mention} is now an antinuke owner.")

    @an_owner.command(name="remove")
    @antinuke_owner_check()
    async def an_owner_remove(self, ctx, user: discord.Member):
        await self.bot.db.execute("DELETE FROM antinuke_owners WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, user.id))
        await ctx.send(f"{user.mention} is no longer an antinuke owner.")

    @antinuke.group(name="admin", invoke_without_command=True)
    async def an_admin(self, ctx):
        await ctx.send("`~antinuke admin add @user` / `~antinuke admin remove @user`")

    @an_admin.command(name="add")
    @antinuke_owner_check()
    async def an_admin_add(self, ctx, user: discord.Member):
        await self.bot.db.execute("INSERT OR IGNORE INTO antinuke_admins (guild_id, user_id) VALUES (?, ?)", (ctx.guild.id, user.id))
        await ctx.send(f"{user.mention} is now an antinuke admin.")

    @an_admin.command(name="remove")
    @antinuke_owner_check()
    async def an_admin_remove(self, ctx, user: discord.Member):
        await self.bot.db.execute("DELETE FROM antinuke_admins WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, user.id))
        await ctx.send(f"{user.mention} is no longer an antinuke admin.")

    @antinuke.group(name="whitelist", aliases=["wl"], invoke_without_command=True)
    async def an_whitelist(self, ctx):
        await ctx.send("`~antinuke wl add @user_or_bot` / `~antinuke wl remove @user_or_bot`")

    @an_whitelist.command(name="add")
    async def an_wl_add(self, ctx, target: discord.Member):
        from config.owner import Me
        is_bot_owner = ctx.author.id in Me or await ctx.bot.is_owner(ctx.author)

        if target.bot:
            is_owner_ish = ctx.author.id == ctx.guild.owner_id or is_bot_owner
            if not is_owner_ish:
                await ctx.send("Only the server owner or bot owner can whitelist a bot.")
                return
        else:
            if not is_bot_owner and not await an.is_antinuke_admin(self.bot, ctx.guild, ctx.author):
                await ctx.send("You need antinuke admin or higher to whitelist users.")
                return

        await an.add_whitelist(self.bot, ctx.guild.id, target.id)
        await ctx.send(f"{target.mention} is now whitelisted from antinuke.")

    @an_whitelist.command(name="remove")
    @antinuke_admin_check()
    async def an_wl_remove(self, ctx, target: discord.Member):
        await an.remove_whitelist(self.bot, ctx.guild.id, target.id)
        await ctx.send(f"{target.mention} is no longer whitelisted.")

    @antinuke.command(name="logchannel")
    @antinuke_owner_check()
    async def an_logchannel(self, ctx, channel: discord.TextChannel):
        await an.set_log_channel(self.bot, ctx.guild.id, channel.id)
        await ctx.send(f"Antinuke log channel set to {channel.mention}.")

async def setup(bot):
    await bot.add_cog(Antinuke(bot))
