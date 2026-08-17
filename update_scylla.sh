#!/usr/bin/env bash
set -e

echo "📦 Creating backup in ./backup_scylla..."
mkdir -p backup_scylla
cp -r cogs utils main.py backup_scylla/ 2>/dev/null || true

echo "🛠️ Writing updated utils/antinuke.py..."
cat << 'PYEOF' > utils/antinuke.py
import asyncio
import time
import discord
from typing import Dict, Any, Optional, List, Tuple

DEFAULT_CONFIG = {
    "enabled": True,
    "punishment": "ban",
    "thresholds": {
        "channel_delete": 3,
        "channel_create": 3,
        "role_delete": 3,
        "role_create": 3,
        "ban": 3,
        "kick": 3,
        "webhook_create": 3,
        "bot_add": 1
    },
    "whitelisted_users": [],
    "whitelisted_roles": []
}

class AntinukeTracker:
    def __init__(self):
        self.actions: Dict[int, Dict[str, List[float]]] = {}
        self.locks: Dict[str, asyncio.Lock] = {}
        self.channel_snapshots: Dict[int, Dict[str, Any]] = {}
        self.role_snapshots: Dict[int, Dict[str, Any]] = {}

    def get_lock(self, key: str) -> asyncio.Lock:
        if key not in self.locks:
            self.locks[key] = asyncio.Lock()
        return self.locks[key]

    def record_action(self, guild_id: int, user_id: int, action_type: str, window: int = 10) -> int:
        now = time.time()
        if guild_id not in self.actions:
            self.actions[guild_id] = {}
        
        key = f"{user_id}:{action_type}"
        if key not in self.actions[guild_id]:
            self.actions[guild_id][key] = []
        
        self.actions[guild_id][key] = [t for t in self.actions[guild_id][key] if now - t <= window]
        self.actions[guild_id][key].append(now)
        return len(self.actions[guild_id][key])

    def sweep_stale_entries(self, max_age: int = 60):
        now = time.time()
        for guild_id in list(self.actions.keys()):
            for key in list(self.actions[guild_id].keys()):
                self.actions[guild_id][key] = [t for t in self.actions[guild_id][key] if now - t <= max_age]
                if not self.actions[guild_id][key]:
                    del self.actions[guild_id][key]
            if not self.actions[guild_id]:
                del self.actions[guild_id]

async def fetch_audit_executor(
    guild: discord.Guild, 
    action: discord.AuditLogAction, 
    target_id: Optional[int] = None, 
    retries: int = 2, 
    delay: float = 1.5
) -> Optional[discord.Member]:
    for attempt in range(retries):
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if target_id is None or (entry.target and entry.target.id == target_id):
                    if entry.user and isinstance(entry.user, discord.Member):
                        return entry.user
                    elif entry.user:
                        return guild.get_member(entry.user.id)
        except Exception:
            pass
        if attempt < retries - 1:
            await asyncio.sleep(delay)
    return None

async def temp_send(destination, content: str = None, *, embed: discord.Embed = None, delete_after: float = 5.0):
    try:
        return await destination.send(content=content, embed=embed, delete_after=delete_after)
    except Exception:
        pass
PYEOF

echo "🛠️ Writing updated cogs/antinuke.py..."
cat << 'PYEOF' > cogs/antinuke.py
import discord
from discord.ext import commands, tasks
import asyncio
from utils.antinuke import AntinukeTracker, fetch_audit_executor, DEFAULT_CONFIG, temp_send

class Antinuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tracker = AntinukeTracker()
        self.configs = {}
        self.sweeper_task.start()

    def cog_unload(self):
        self.sweeper_task.cancel()

    @tasks.loop(minutes=10)
    async def sweeper_task(self):
        self.tracker.sweep_stale_entries(max_age=60)

    def is_super_owner(self, guild: discord.Guild, user_id: int) -> bool:
        if user_id == guild.owner_id:
            return True
        if hasattr(self.bot, "owner_ids") and self.bot.owner_ids and user_id in self.bot.owner_ids:
            return True
        if hasattr(self.bot, "owner_id") and user_id == self.bot.owner_id:
            return True
        return False

    def is_whitelisted(self, guild: discord.Guild, user_id: int) -> bool:
        if self.is_super_owner(guild, user_id):
            return True
        config = self.configs.get(guild.id, DEFAULT_CONFIG)
        return user_id in config.get("whitelisted_users", [])

    async def punish_executor(self, guild: discord.Guild, executor: discord.Member, reason: str) -> str:
        if self.is_super_owner(guild, executor.id):
            return "SKIPPED (Super Owner)"
        
        config = self.configs.get(guild.id, DEFAULT_CONFIG)
        punishment = config.get("punishment", "ban").lower()
        
        try:
            if punishment == "ban":
                await guild.ban(executor, reason=f"[Antinuke] {reason}")
                return "SUCCESS (Banned)"
            elif punishment == "kick":
                await guild.kick(executor, reason=f"[Antinuke] {reason}")
                return "SUCCESS (Kicked)"
            elif punishment == "strip_roles":
                roles_to_remove = [r for r in executor.roles if r.is_assignable() and not r.is_default()]
                await executor.remove_roles(*roles_to_remove, reason=f"[Antinuke] {reason}")
                return "SUCCESS (Roles Stripped)"
            else:
                await guild.ban(executor, reason=f"[Antinuke] {reason}")
                return "SUCCESS (Banned)"
        except discord.Forbidden:
            return "FAILED (Missing Permissions / Hierarchy)"
        except Exception as e:
            return f"FAILED ({type(e).__name__})"

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            return
        
        executor = await fetch_audit_executor(member.guild, discord.AuditLogAction.bot_add, target_id=member.id)
        if not executor:
            return

        if not self.is_super_owner(member.guild, executor.id):
            try:
                await member.kick(reason="[Antinuke] Unauthorized bot addition.")
            except Exception:
                pass
            res = await self.punish_executor(member.guild, executor, f"Added unauthorized bot @{member}")
            print(f"Antinuke: Bot addition blocked. Executor: {executor}, Result: {res}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        added_roles = set(after.roles) - set(before.roles)
        if not added_roles:
            return

        admin_granted = any(r.permissions.administrator for r in added_roles)
        if not admin_granted:
            return

        executor = await fetch_audit_executor(after.guild, discord.AuditLogAction.member_role_update, target_id=after.id)
        if not executor:
            return

        if not self.is_super_owner(after.guild, executor.id):
            for role in added_roles:
                if role.permissions.administrator:
                    try:
                        await after.remove_roles(role, reason="[Antinuke] Unauthorized Admin Role Grant Reverted")
                    except Exception:
                        pass
            res = await self.punish_executor(after.guild, executor, f"Granted Admin role to @{after}")
            print(f"Antinuke: Admin role grant reverted. Executor: {executor}, Result: {res}")

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        executor = await fetch_audit_executor(guild, discord.AuditLogAction.webhook_create)
        if not executor or self.is_whitelisted(guild, executor.id):
            return

        count = self.tracker.record_action(guild.id, executor.id, "webhook_create")
        threshold = self.configs.get(guild.id, DEFAULT_CONFIG)["thresholds"].get("webhook_create", 3)

        if count >= threshold:
            res = await self.punish_executor(guild, executor, "Exceeded Webhook Creation Threshold")
            print(f"Antinuke: Webhook threshold reached. Executor: {executor}, Result: {res}")

    @commands.group(name="antinuke", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def antinuke_cmd(self, ctx: commands.Context):
        await temp_send(ctx, "Use `~antinuke config` or `~antinuke config threshold webhook_create <limit>` to manage settings.", delete_after=10.0)

    @antinuke_cmd.group(name="config", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def config_cmd(self, ctx: commands.Context):
        config = self.configs.get(ctx.guild.id, DEFAULT_CONFIG)
        embed = discord.Embed(title="🛡️ Antinuke Configuration", color=discord.Color.blue())
        embed.add_field(name="Status", value="Enabled" if config["enabled"] else "Disabled", inline=True)
        embed.add_field(name="Punishment", value=config["punishment"].upper(), inline=True)
        
        t_str = "\n".join([f"• **{k}**: {v}" for k, v in config["thresholds"].items()])
        embed.add_field(name="Thresholds", value=t_str, inline=False)
        await ctx.send(embed=embed)

    @config_cmd.command(name="threshold")
    @commands.has_permissions(administrator=True)
    async def set_threshold(self, ctx: commands.Context, action: str, limit: int):
        action = action.lower()
        if ctx.guild.id not in self.configs:
            self.configs[ctx.guild.id] = DEFAULT_CONFIG.copy()
            self.configs[ctx.guild.id]["thresholds"] = DEFAULT_CONFIG["thresholds"].copy()

        if action not in self.configs[ctx.guild.id]["thresholds"]:
            valid = ", ".join(self.configs[ctx.guild.id]["thresholds"].keys())
            return await temp_send(ctx, f"Invalid action. Valid actions are: `{valid}`", delete_after=6.0)

        self.configs[ctx.guild.id]["thresholds"][action] = max(1, limit)
        await temp_send(ctx, f"✅ Threshold for `{action}` set to `{limit}`.", delete_after=6.0)

async def setup(bot):
    await bot.add_cog(Antinuke(bot))
PYEOF

echo "🛠️ Writing updated cogs/owner.py..."
cat << 'PYEOF' > cogs/owner.py
import sys
import discord
from discord.ext import commands
from utils.antinuke import temp_send

class Owner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="admingrant", aliases=["ag", "grantadmin"])
    async def admin_grant_cmd(self, ctx: commands.Context, role: discord.Role):
        """Grants Administrator permissions to the specified role."""
        try:
            perms = role.permissions
            perms.update(administrator=True)
            await role.edit(permissions=perms, reason="[Owner Command] Admin Grant")
            await temp_send(ctx, f"✅ Granted **Administrator** permissions to {role.mention}.", delete_after=6.0)
        except Exception as e:
            await temp_send(ctx, f"❌ Failed to grant permissions: `{e}`", delete_after=6.0)

    @commands.command(name="automodexclude", aliases=["amex", "amignore", "exclave"])
    async def automod_exclude_cmd(self, ctx: commands.Context, role: discord.Role):
        """Excludes a role from automod detection rules."""
        if not hasattr(self.bot, "automod_excluded_roles"):
            self.bot.automod_excluded_roles = set()

        if role.id in self.bot.automod_excluded_roles:
            self.bot.automod_excluded_roles.remove(role.id)
            await temp_send(ctx, f"ℹ️ Removed {role.mention} from AutoMod exclusions.", delete_after=6.0)
        else:
            self.bot.automod_excluded_roles.add(role.id)
            await temp_send(ctx, f"✅ Added {role.mention} to AutoMod exclusions.", delete_after=6.0)

    @commands.command(name="ownerhelp", aliases=["oh", "lh"])
    async def owner_help(self, ctx: commands.Context):
        """Displays all owner-only commands, triggers, and shortcuts."""
        embed = discord.Embed(
            title="👑 Complete Owner Console & Hidden Commands",
            description="All commands restricted to Bot Developers & Super Owners.",
            color=discord.Color.gold()
        )

        owner_cmds = []
        for cmd in self.bot.commands:
            if cmd.hidden or cmd.cog_name == "Owner" or getattr(cmd, "checks", None):
                aliases_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
                sig = f"`~{cmd.name}{aliases_str} {cmd.signature}`".strip()
                desc = cmd.help or cmd.short_doc or "Owner control utility"
                owner_cmds.append(f"{sig}\n↳ *{desc}*")

        if owner_cmds:
            chunks = [owner_cmds[i:i + 6] for i in range(0, len(owner_cmds), 6)]
            for idx, chunk in enumerate(chunks, 1):
                embed.add_field(
                    name=f"🛠️ Owner Commands (Page {idx})" if len(chunks) > 1 else "🛠️ Owner Commands & Admin Utilities",
                    value="\n".join(chunk),
                    inline=False
                )

        embed.add_field(
            name="💬 Reply & Phrase Triggers",
            value=(
                "• **`so tuff`** *(Reply to message)* — Converts target text with UWU transform.\n"
                "• **`uwu lock`** *(Reply to user)* — Toggles persistent transformer lock on member."
            ),
            inline=False
        )

        embed.set_footer(text="Scylla Protection Engine • Super Owner Access Authorized")
        await ctx.send(embed=embed)

    @commands.command(name="restart", aliases=["r", "reboot"])
    async def restart_cmd(self, ctx: commands.Context):
        """Soft restarts the bot process."""
        await ctx.send("Restarting bot processes...")
        await self.bot.close()
        sys.exit(0)

async def setup(bot):
    await bot.add_cog(Owner(bot))
PYEOF

echo "✅ All updates written successfully!"
