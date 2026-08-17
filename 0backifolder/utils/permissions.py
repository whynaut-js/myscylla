import discord
from datetime import datetime
from config.owner import Me

BOOLEAN_PERMS = {
    "view",
    "kick",
    "ban",
    "mute",
    "jail",
    "manage_channels",
    "manage_roles",
    "pingroles",
}


async def _is_immortal(bot, guild: discord.Guild, member: discord.Member) -> bool:
    """Bot owner or this server's owner — always bypasses every bot-perm check."""
    if member.id == guild.owner_id:
        return True
    if member.id in Me or await bot.is_owner(member):
        return True
    return False


async def has_botperm(bot, guild: discord.Guild, member: discord.Member, perm_name: str) -> bool:
    """Check whether a member has a given bot-perm, directly or via a role."""
    if await _is_immortal(bot, guild, member):
        return True

    ids_to_check = [member.id] + [role.id for role in member.roles]
    for target_id in ids_to_check:
        row = await bot.db.fetchone(
            "SELECT 1 FROM fake_perms WHERE guild_id = ? AND target_id = ? AND perm_name = ?",
            (guild.id, target_id, perm_name),
        )
        if row is not None:
            return True

    return False


async def can_ping_role(bot, guild: discord.Guild, member: discord.Member, role: discord.Role) -> bool:
    """Check whether a member is allowed to ping a specific role via the bot."""
    if await _is_immortal(bot, guild, member):
        return True

    if await has_botperm(bot, guild, member, "pingroles"):
        return True

    ids_to_check = [member.id] + [r.id for r in member.roles]
    for target_id in ids_to_check:
        row = await bot.db.fetchone(
            "SELECT 1 FROM pingable_roles WHERE guild_id = ? AND target_id = ? AND role_id = ?",
            (guild.id, target_id, role.id),
        )
        if row is not None:
            return True

    return False


async def get_pingrole_cooldown_seconds(bot, guild: discord.Guild, member: discord.Member, role: discord.Role):
    """Specific-role cooldown takes priority over blanket cooldown. None = unlimited."""
    ids_to_check = [member.id] + [r.id for r in member.roles]

    for target_id in ids_to_check:
        row = await bot.db.fetchone(
            "SELECT cooldown_seconds FROM pingrole_cooldown_config WHERE guild_id = ? AND target_id = ? AND role_id = ?",
            (guild.id, target_id, role.id),
        )
        if row is not None:
            return row[0]

    for target_id in ids_to_check:
        row = await bot.db.fetchone(
            "SELECT cooldown_seconds FROM pingrole_cooldown_config WHERE guild_id = ? AND target_id = ? AND role_id IS NULL",
            (guild.id, target_id),
        )
        if row is not None:
            return row[0]

    return None


async def check_pingrole_cooldown(bot, guild: discord.Guild, member: discord.Member, role: discord.Role):
    """Returns (allowed: bool, seconds_remaining: int or None)."""
    if await _is_immortal(bot, guild, member):
        return True, None

    cooldown_seconds = await get_pingrole_cooldown_seconds(bot, guild, member, role)
    if cooldown_seconds is None:
        return True, None

    row = await bot.db.fetchone(
        "SELECT last_used_at FROM pingrole_last_used WHERE guild_id = ? AND user_id = ? AND role_id = ?",
        (guild.id, member.id, role.id),
    )
    if row is None:
        return True, None

    last_used = datetime.fromisoformat(row[0])
    elapsed = (datetime.utcnow() - last_used).total_seconds()
    remaining = cooldown_seconds - elapsed
    if remaining > 0:
        return False, int(remaining)
    return True, None


async def record_pingrole_use(bot, guild: discord.Guild, member: discord.Member, role: discord.Role):
    now = datetime.utcnow().isoformat()
    await bot.db.execute(
        """
        INSERT INTO pingrole_last_used (guild_id, user_id, role_id, last_used_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id, role_id) DO UPDATE SET last_used_at = excluded.last_used_at
        """,
        (guild.id, member.id, role.id, now),
    )
