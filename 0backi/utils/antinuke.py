import discord
import time
import json
import asyncio
from collections import defaultdict
from config.owner import Me

DEFAULT_CONFIG = {
    "channel_delete": {"count": 2, "window": 10},
    "channel_create": {"count": 2, "window": 10},
    "role_delete": {"count": 2, "window": 10},
    "ban": {"count": 2, "window": 10},
    "kick": {"count": 2, "window": 10},
    "webhook_create": {"count": 2, "window": 10},
    "everyone_ping": {"count": 1, "window": 10}
}

tracker = {}
instant_channel_cache = {}
event_cache = {}  # {guild_id: {user_id: {action: [(payload, timestamp), ...]}}}
_locks = defaultdict(asyncio.Lock)

async def get_config(bot, guild_id: int):
    row = await bot.db.fetchone(
        "SELECT enabled, log_channel_id, punishment, thresholds_json FROM antinuke_config WHERE guild_id = ?",
        (guild_id,)
    )
    if not row:
        return {"enabled": 0, "log_channel_id": None, "punishment": "strip", "thresholds": DEFAULT_CONFIG.copy()}

    thresholds = DEFAULT_CONFIG.copy()
    if row[3]:
        try:
            saved = json.loads(row[3])
            for k, v in saved.items():
                if isinstance(v, int):
                    thresholds[k] = {"count": v, "window": 10}
                elif isinstance(v, dict):
                    thresholds[k] = v
        except Exception:
            pass

    return {
        "enabled": bool(row[0]),
        "log_channel_id": row[1],
        "punishment": row[2] or "strip",
        "thresholds": thresholds
    }

async def set_punishment(bot, guild_id: int, punishment: str):
    await bot.db.execute(
        "INSERT INTO antinuke_config (guild_id, punishment) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET punishment = excluded.punishment",
        (guild_id, punishment)
    )

async def set_threshold(bot, guild_id: int, action: str, count: int, window: int = 10):
    config = await get_config(bot, guild_id)
    t = config["thresholds"]
    t[action] = {"count": count, "window": window}
    await bot.db.execute(
        "INSERT INTO antinuke_config (guild_id, thresholds_json) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET thresholds_json = excluded.thresholds_json",
        (guild_id, json.dumps(t))
    )

async def is_antinuke_owner(bot, guild: discord.Guild, user: discord.User) -> bool:
    if user.id == guild.owner_id:
        return True
    row = await bot.db.fetchone(
        "SELECT 1 FROM antinuke_owners WHERE guild_id = ? AND user_id = ?",
        (guild.id, user.id)
    )
    return row is not None

async def is_antinuke_admin(bot, guild: discord.Guild, user: discord.User) -> bool:
    if await is_antinuke_owner(bot, guild, user):
        return True
    row = await bot.db.fetchone(
        "SELECT 1 FROM antinuke_admins WHERE guild_id = ? AND user_id = ?",
        (guild.id, user.id)
    )
    return row is not None

async def is_whitelisted(bot, guild: discord.Guild, user: discord.User) -> bool:
    # FIX #2: bot owner / config.owner.Me now always bypass antinuke, everywhere —
    # matches the same global bypass every command already has, which this
    # (being event-driven, not a command) previously did NOT inherit.
    if user.id in Me or await bot.is_owner(user):
        return True
    if user.id == bot.user.id or await is_antinuke_admin(bot, guild, user):
        return True
    row = await bot.db.fetchone(
        "SELECT 1 FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ?",
        (guild.id, user.id)
    )
    return row is not None

async def get_executor(guild: discord.Guild, action: discord.AuditLogAction, target_id: int = None, retry: bool = True):
    # FIX #6: audit logs can lag a second or two behind the actual event.
    # One short retry catches most of those races instead of silently
    # returning None and letting the action go unattributed.
    async def _lookup():
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if target_id is None or (entry.target and entry.target.id == target_id):
                    return entry.user
        except Exception:
            pass
        return None

    result = await _lookup()
    if result is None and retry:
        await asyncio.sleep(1.5)
        result = await _lookup()
    return result

async def punish(guild: discord.Guild, executor: discord.Member, config_punishment: str, reason: str) -> tuple[bool, str]:
    """Returns (success, actual_punishment_applied) so callers can log the truth
    instead of assuming the configured punishment always worked."""
    actual_punishment = "ban" if executor.bot else config_punishment

    if actual_punishment == "ban":
        try:
            await guild.ban(executor, reason=reason)
            return True, "ban"
        except Exception:
            return False, "ban (FAILED — check bot's role position vs offender's role)"
    elif actual_punishment == "kick":
        try:
            await executor.kick(reason=reason)
            return True, "kick"
        except Exception:
            return False, "kick (FAILED — check bot's role position vs offender's role)"
    else:
        try:
            dangerous_perms = ["administrator", "manage_guild", "manage_roles", "manage_channels", "ban_members", "kick_members"]
            roles_to_remove = [
                role for role in executor.roles
                if not role.is_default() and role < guild.me.top_role and any(getattr(role.permissions, perm) for perm in dangerous_perms)
            ]
            if roles_to_remove:
                await executor.remove_roles(*roles_to_remove, reason=reason)
                return True, "strip"
            return False, "strip (no dangerous roles found, or all above bot's role)"
        except Exception:
            return False, "strip (FAILED — check bot's role position vs offender's role)"

async def log_action(bot, guild: discord.Guild, executor: discord.User, action: str, details: str, punish_label: str = None):
    config = await get_config(bot, guild.id)
    if not config["log_channel_id"]:
        return
    log_channel = guild.get_channel(config["log_channel_id"])
    if not log_channel:
        return

    # FIX #1: use the ACTUAL result of the punishment attempt, not just the
    # configured setting — previously this always said e.g. "ban" even if
    # the ban silently failed, contradicting the ✅/⚠️ status in `details`.
    applied_punishment = punish_label if punish_label is not None else "N/A"

    embed = discord.Embed(
        title="🚨 ANTINUKE TRIGGERED",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="Offender", value=f"{executor.mention} (`{executor.id}`)", inline=False)
    embed.add_field(name="Action Type", value=f"`{action}`", inline=True)
    embed.add_field(name="Punishment Applied", value=f"`{applied_punishment}`", inline=True)
    embed.add_field(name="Details & Rollback", value=details, inline=False)

    try:
        await log_channel.send(embed=embed)
    except Exception:
        pass

async def track_channel_creation(guild_id: int, user_id: int, channel_id: int):
    now = time.time()
    g_cache = instant_channel_cache.setdefault(guild_id, {})
    u_cache = g_cache.setdefault(user_id, [])
    u_cache.append((channel_id, now))

async def track_event(guild_id: int, user_id: int, action: str, payload: dict):
    """Records a payload (e.g. deleted-channel/role info) the moment it happens,
    so if the threshold is crossed later in the same window, EVERYTHING that
    happened during the window can be rolled back — not just the one event
    that happened to trip the threshold."""
    now = time.time()
    g_cache = event_cache.setdefault(guild_id, {})
    u_cache = g_cache.setdefault(user_id, {})
    a_cache = u_cache.setdefault(action, [])
    a_cache.append((payload, now))

def _pop_cached_events(guild_id: int, user_id: int, action: str, window_seconds: int):
    g_cache = event_cache.get(guild_id, {})
    u_cache = g_cache.get(user_id, {})
    entries = u_cache.pop(action, [])
    now = time.time()
    return [payload for payload, t in entries if now - t <= window_seconds + 5]

async def strip_everyone_perm(guild: discord.Guild, member: discord.Member):
    """Immediately revokes 'mention_everyone' from every role the offender has,
    so any further pings they queue up (before the ban/kick/strip lands) fail
    outright instead of sending. Only touches roles below the bot's own role."""
    for role in member.roles:
        if role.is_default() or role >= guild.me.top_role:
            continue
        if role.permissions.mention_everyone:
            try:
                new_perms = discord.Permissions(role.permissions.value)
                new_perms.mention_everyone = False
                await role.edit(permissions=new_perms, reason="Antinuke: revoked after @everyone spam")
            except Exception:
                pass

async def _restore_channel(guild: discord.Guild, info: dict):
    category = guild.get_channel(info.get("category_id")) if info.get("category_id") else None

    overwrites = {}
    for ow in info.get("overwrites", []):
        target = None
        if ow["target_type"] == "role":
            target = guild.get_role(ow["target_id"])
        else:
            target = guild.get_member(ow["target_id"])
        if target:
            overwrites[target] = discord.PermissionOverwrite.from_pair(
                discord.Permissions(ow["allow"]), discord.Permissions(ow["deny"])
            )

    kwargs = {"category": category, "overwrites": overwrites, "reason": "Antinuke Rollback"}
    if info.get("type") == discord.ChannelType.voice:
        new_channel = await guild.create_voice_channel(info["name"], **kwargs)
    else:
        new_channel = await guild.create_text_channel(info["name"], **kwargs)
        try:
            await new_channel.edit(
                topic=info.get("topic"),
                slowmode_delay=info.get("slowmode_delay", 0) or 0,
                nsfw=info.get("nsfw", False),
            )
        except Exception:
            pass

    try:
        await new_channel.edit(position=info.get("position", 0))
    except Exception:
        pass

    return new_channel

async def _restore_role(guild: discord.Guild, info: dict):
    new_role = await guild.create_role(
        name=info["name"],
        permissions=discord.Permissions(info["permissions"]),
        color=discord.Color(info["color"]),
        hoist=info["hoist"],
        mentionable=info["mentionable"],
        reason="Antinuke Rollback"
    )

    try:
        await new_role.edit(position=info.get("position", 0))
    except Exception:
        pass

    reassigned = 0
    for member_id in info.get("member_ids", []):
        member = guild.get_member(member_id)
        if member:
            try:
                await member.add_roles(new_role, reason="Antinuke Rollback: restoring deleted role")
                reassigned += 1
            except Exception:
                pass

    return new_role, reassigned

async def handle_detected(bot, guild: discord.Guild, executor: discord.User, action: str, details: str, target_obj=None):
    if not executor or executor.id == bot.user.id:
        return
    if await is_whitelisted(bot, guild, executor):
        return

    config = await get_config(bot, guild.id)
    if not config["enabled"]:
        return

    lock_key = (guild.id, executor.id, action)
    async with _locks[lock_key]:
        now = time.time()
        action_cfg = config["thresholds"].get(action, {"count": 2, "window": 10})
        count_limit = action_cfg["count"]
        window_seconds = action_cfg["window"]

        guild_tracker = tracker.setdefault(guild.id, {})
        user_tracker = guild_tracker.setdefault(executor.id, {})
        timestamps = user_tracker.get(action, [])

        timestamps = [t for t in timestamps if now - t <= window_seconds]
        timestamps.append(now)

        if len(timestamps) >= count_limit:
            user_tracker.pop(action, None)
            member = guild.get_member(executor.id)
            punish_success, punish_label = (False, "N/A (member left already)")
            if member:
                punish_success, punish_label = await punish(guild, member, config["punishment"], f"Antinuke: {action} threshold reached")

            rollback_msg = details
            status_icon = "✅" if punish_success else "⚠️"
            rollback_msg += f"\n{status_icon} **Punishment:** `{punish_label}`"

            if action == "channel_create":
                g_cache = instant_channel_cache.get(guild.id, {})
                u_cache = g_cache.pop(executor.id, [])
                valid_channels = [c_id for c_id, t in u_cache if now - t <= window_seconds + 5]

                deleted_count = 0
                for c_id in valid_channels:
                    ch = guild.get_channel(c_id)
                    if ch:
                        try:
                            await ch.delete(reason="Antinuke Rollback: wiping spam channel")
                            deleted_count += 1
                        except Exception:
                            pass
                rollback_msg += f"\n🧹 **Rollback:** Retroactively deleted {deleted_count} spam channel(s)."

            elif action == "channel_delete":
                payloads = _pop_cached_events(guild.id, executor.id, action, window_seconds)
                if not payloads and isinstance(target_obj, dict):
                    payloads = [target_obj]

                recreated = 0
                for info in payloads:
                    try:
                        await _restore_channel(guild, info)
                        recreated += 1
                    except Exception:
                        pass
                rollback_msg += f"\n♻️ **Rollback:** Recreated {recreated} deleted channel(s) (name, permissions, topic, slowmode restored)."

            elif action == "role_delete":
                payloads = _pop_cached_events(guild.id, executor.id, action, window_seconds)
                if not payloads and isinstance(target_obj, dict):
                    payloads = [target_obj]

                recreated = 0
                total_reassigned = 0
                for info in payloads:
                    try:
                        _, reassigned = await _restore_role(guild, info)
                        recreated += 1
                        total_reassigned += reassigned
                    except Exception:
                        pass
                rollback_msg += f"\n♻️ **Rollback:** Recreated {recreated} deleted role(s), reassigned to {total_reassigned} member(s)."

            await log_action(bot, guild, executor, action, rollback_msg, punish_label=punish_label)
        else:
            user_tracker[action] = timestamps

        if not user_tracker.get(action):
            user_tracker.pop(action, None)
        if not user_tracker:
            guild_tracker.pop(executor.id, None)
        if not guild_tracker:
            tracker.pop(guild.id, None)

async def handle_detected_instant(bot, guild: discord.Guild, executor: discord.User, details: str):
    if not executor or executor.id == bot.user.id:
        return
    if await is_whitelisted(bot, guild, executor):
        return

    config = await get_config(bot, guild.id)
    if not config["enabled"]:
        return

    member = guild.get_member(executor.id)
    punish_success, punish_label = (False, "N/A (member left already)")
    if member:
        punish_success, punish_label = await punish(guild, member, config["punishment"], "Antinuke: instant trigger")

    status_icon = "✅" if punish_success else "⚠️"
    await log_action(bot, guild, executor, "Instant Protection", f"{details}\n{status_icon} **Punishment:** `{punish_label}`", punish_label=punish_label)

async def cleanup_stale_entries(max_age_seconds: int = 3600):
    """FIX #4: memory leak fix. Anything sitting in the trackers/caches for
    longer than max_age_seconds gets dropped — previously entries only got
    cleared when a threshold was actually crossed, so users who stayed just
    under the limit accumulated forever on a long-running bot. Also prunes
    unheld locks so _locks doesn't grow forever either."""
    now = time.time()

    for guild_id in list(tracker.keys()):
        for user_id in list(tracker[guild_id].keys()):
            for action in list(tracker[guild_id][user_id].keys()):
                tracker[guild_id][user_id][action] = [
                    t for t in tracker[guild_id][user_id][action] if now - t <= max_age_seconds
                ]
                if not tracker[guild_id][user_id][action]:
                    tracker[guild_id][user_id].pop(action, None)
            if not tracker[guild_id][user_id]:
                tracker[guild_id].pop(user_id, None)
        if not tracker[guild_id]:
            tracker.pop(guild_id, None)

    for guild_id in list(instant_channel_cache.keys()):
        for user_id in list(instant_channel_cache[guild_id].keys()):
            instant_channel_cache[guild_id][user_id] = [
                (c_id, t) for c_id, t in instant_channel_cache[guild_id][user_id] if now - t <= max_age_seconds
            ]
            if not instant_channel_cache[guild_id][user_id]:
                instant_channel_cache[guild_id].pop(user_id, None)
        if not instant_channel_cache[guild_id]:
            instant_channel_cache.pop(guild_id, None)

    for guild_id in list(event_cache.keys()):
        for user_id in list(event_cache[guild_id].keys()):
            for action in list(event_cache[guild_id][user_id].keys()):
                event_cache[guild_id][user_id][action] = [
                    (p, t) for p, t in event_cache[guild_id][user_id][action] if now - t <= max_age_seconds
                ]
                if not event_cache[guild_id][user_id][action]:
                    event_cache[guild_id][user_id].pop(action, None)
            if not event_cache[guild_id][user_id]:
                event_cache[guild_id].pop(user_id, None)
        if not event_cache[guild_id]:
            event_cache.pop(guild_id, None)

    for key in list(_locks.keys()):
        if not _locks[key].locked():
            _locks.pop(key, None)
