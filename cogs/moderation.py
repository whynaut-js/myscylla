import discord
from discord.ext import commands
from utils.checks import is_server_owner, is_top_tier
from utils.permissions import has_botperm
from utils.duration import parse_duration
from utils.modlog import log_case
from utils.confirm import ask_confirm
from utils.setup_helpers import ask_role, ask_channel
from utils import antinuke as an
from utils.autodelete import send_temp

class Moderation(commands.Cog):
    """Kick, ban, timeout, and jail — all gated by bot-perms, all logged as cases."""

    def __init__(self, bot):
        self.bot = bot
        self.recent_messages = {}

    async def _get_jail_config(self, guild_id):
        row = await self.bot.db.fetchone(
            "SELECT jail_role_id, appeal_channel_id FROM guild_config WHERE guild_id = ?",
            (guild_id,),
        )
        return row if row else (None, None)

    async def cog_load(self):
        """Ensure database table exists to store original roles for jailed users."""
        await self.bot.db.execute(
            """
            CREATE TABLE IF NOT EXISTS jailed_user_roles (
                guild_id INTEGER,
                user_id INTEGER,
                role_ids TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

    @commands.command(name="jailsetup", aliases=["js"])
    @is_server_owner()
    async def jailsetup(self, ctx):
        """Configure (or reconfigure) jail — asks for your Jailed role and appeal channel every time. Safe to re-run to change them."""
        jail_role = await ask_role(ctx, "Jailed")
        if jail_role is None:
            jail_role = await ctx.guild.create_role(
                name="Jailed", permissions=discord.Permissions.none(), reason="Jail system setup"
            )
            for channel in ctx.guild.channels:
                try:
                    await channel.set_permissions(jail_role, view_channel=False, reason="Jail system setup")
                except discord.Forbidden:
                    pass

        appeal_channel = await ask_channel(ctx, "jail appeals")
        if appeal_channel is None:
            appeal_channel = await ctx.guild.create_text_channel(
                "jail-appeals",
                overwrites={
                    ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    jail_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                },
                reason="Jail system setup",
            )

        await self.bot.db.execute(
            """
            INSERT INTO guild_config (guild_id, jail_role_id, appeal_channel_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET jail_role_id = excluded.jail_role_id,
                                                 appeal_channel_id = excluded.appeal_channel_id
            """,
            (ctx.guild.id, jail_role.id, appeal_channel.id),
        )

        await ctx.send(f"Jail configured: {jail_role.mention} role, {appeal_channel.mention} channel.")

    @commands.command(name="kick", aliases=["k"])
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Kick a member. Example: ~kick @user spamming"""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "kick"):
            await send_temp(ctx, "You don't have permission to kick.")
            return
        if not await ask_confirm(ctx, f"⚠️ Kick {member.mention}? Reason: {reason}"):
            await send_temp(ctx, "Cancelled.")
            return
        if not await an.check_and_track(self.bot, ctx, "kick", "Mass kicking"):
            return
        await member.kick(reason=reason)
        case_id = await log_case(self.bot, ctx.guild, "kick", ctx.author, member, reason)
        await send_temp(ctx, f"Kicked {member.mention} — {reason} (Case #{case_id})")

    @commands.command(name="ban", aliases=["b"])
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Ban a member. Example: ~ban @user rule violation"""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "ban"):
            await send_temp(ctx, "You don't have permission to ban.")
            return
        if not await ask_confirm(ctx, f"⚠️ Ban {member.mention}? Reason: {reason}"):
            await send_temp(ctx, "Cancelled.")
            return
        if not await an.check_and_track(self.bot, ctx, "ban", "Mass banning"):
            return
        await member.ban(reason=reason)
        case_id = await log_case(self.bot, ctx.guild, "ban", ctx.author, member, reason)
        await send_temp(ctx, f"Banned {member.mention} — {reason} (Case #{case_id})")

    @commands.command(name="softban", aliases=["sb"])
    async def softban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Ban then immediately unban — purges recent messages, lets them rejoin. Example: ~softban @user cleanup"""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "ban"):
            await send_temp(ctx, "You don't have permission to softban.")
            return
        if not await ask_confirm(ctx, f"⚠️ Softban {member.mention}? Reason: {reason}"):
            await send_temp(ctx, "Cancelled.")
            return
        if not await an.check_and_track(self.bot, ctx, "ban", "Mass banning (softban)"):
            return
        await member.ban(reason=f"Softban: {reason}", delete_message_seconds=604800)
        await ctx.guild.unban(member, reason="Softban: auto-unban after purge")
        case_id = await log_case(self.bot, ctx.guild, "softban", ctx.author, member, reason)
        await send_temp(ctx, f"Softbanned {member.mention} — {reason} (Case #{case_id})")

    @commands.command(name="hardban", aliases=["hb"])
    async def hardban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Permanent ban with maximum message purge (7 days). Example: ~hardban @user raid"""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "ban"):
            await send_temp(ctx, "You don't have permission to hardban.")
            return
        if not await ask_confirm(ctx, f"⚠️ Hardban {member.mention} (7-day message purge)? Reason: {reason}"):
            await send_temp(ctx, "Cancelled.")
            return
        if not await an.check_and_track(self.bot, ctx, "ban", "Mass banning (hardban)"):
            return
        await member.ban(reason=f"Hardban: {reason}", delete_message_seconds=604800)
        case_id = await log_case(self.bot, ctx.guild, "hardban", ctx.author, member, reason)
        await send_temp(ctx, f"Hardbanned {member.mention} — {reason} (Case #{case_id})")

    @commands.command(name="timeout", aliases=["to"])
    async def timeout(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        """Timeout a member. Example: ~timeout @user 10m spamming"""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "mute"):
            await send_temp(ctx, "You don't have permission to timeout.")
            return

        delta = parse_duration(duration)
        if delta is None:
            await send_temp(ctx, "Invalid duration. Use formats like `10m`, `1h`, `2d`.")
            return

        try:
            await member.timeout(delta, reason=reason)
            case_id = await log_case(self.bot, ctx.guild, "timeout", ctx.author, member, f"{reason} (duration: {duration})")
            await send_temp(ctx, f"Timed out {member.mention} for {duration} — {reason} (Case #{case_id})")
        except discord.HTTPException:
            await send_temp(ctx, "Couldn't timeout — duration may exceed Discord's 28-day limit.")

    @commands.command(name="jail", aliases=["j"])
    async def jail(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Jail a member — removes all roles and channel access except the appeal channel."""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "jail"):
            await send_temp(ctx, "You don't have permission to jail.")
            return

        jail_role_id, _ = await self._get_jail_config(ctx.guild.id)
        jail_role = ctx.guild.get_role(jail_role_id) if jail_role_id else None
        if jail_role is None:
            await send_temp(ctx, "Jail isn't set up yet — run `~jailsetup` first.")
            return

        # Strip current roles (excluding @everyone, managed roles, and roles above bot's top role)
        roles_to_remove = [
            role for role in member.roles
            if not role.is_default() and not role.managed and role < ctx.guild.me.top_role
        ]

        # Save stripped roles in DB
        role_ids_str = ",".join(str(r.id) for r in roles_to_remove)
        await self.bot.db.execute(
            """
            INSERT INTO jailed_user_roles (guild_id, user_id, role_ids)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET role_ids = excluded.role_ids
            """,
            (ctx.guild.id, member.id, role_ids_str)
        )

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Jailed: {reason}")
            await member.add_roles(jail_role, reason=f"Jailed: {reason}")
        except discord.Forbidden:
            await send_temp(ctx, "Failed to strip/assign roles due to missing permissions or role hierarchy.")
            return

        await self.bot.db.execute(
            """
            INSERT INTO jail_appeals (guild_id, user_id, has_pending_appeal)
            VALUES (?, ?, 0)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET has_pending_appeal = 0
            """,
            (ctx.guild.id, member.id),
        )
        self.recent_messages.pop((ctx.guild.id, member.id), None)
        case_id = await log_case(self.bot, ctx.guild, "jail", ctx.author, member, reason)
        await send_temp(ctx, f"Jailed {member.mention} and stripped roles — {reason} (Case #{case_id})")

    @commands.command(name="unjail", aliases=["uj"])
    async def unjail(self, ctx, member: discord.Member):
        """Remove a member from jail and restore their original roles."""
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "jail"):
            await send_temp(ctx, "You don't have permission to unjail.")
            return

        jail_role_id, appeal_channel_id = await self._get_jail_config(ctx.guild.id)
        jail_role = ctx.guild.get_role(jail_role_id) if jail_role_id else None
        if jail_role and jail_role in member.roles:
            try:
                await member.remove_roles(jail_role, reason="Unjailed")
            except discord.Forbidden:
                pass

        # Restore original roles from DB
        row = await self.bot.db.fetchone(
            "SELECT role_ids FROM jailed_user_roles WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, member.id)
        )
        if row and row[0]:
            saved_role_ids = [int(rid) for rid in row[0].split(",") if rid]
            roles_to_restore = [
                ctx.guild.get_role(rid) for rid in saved_role_ids
                if ctx.guild.get_role(rid) and ctx.guild.get_role(rid) < ctx.guild.me.top_role
            ]
            if roles_to_restore:
                try:
                    await member.add_roles(*roles_to_restore, reason="Unjailed: restoring original roles")
                except discord.Forbidden:
                    pass

            await self.bot.db.execute(
                "DELETE FROM jailed_user_roles WHERE guild_id = ? AND user_id = ?",
                (ctx.guild.id, member.id)
            )

        appeal_channel = ctx.guild.get_channel(appeal_channel_id) if appeal_channel_id else None
        if appeal_channel:
            try:
                await appeal_channel.set_permissions(member, overwrite=None)
            except discord.Forbidden:
                pass

        await self.bot.db.execute(
            "UPDATE jail_appeals SET has_pending_appeal = 0 WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, member.id),
        )
        self.recent_messages.pop((ctx.guild.id, member.id), None)
        case_id = await log_case(self.bot, ctx.guild, "unjail", ctx.author, member, "Released from jail")
        await send_temp(ctx, f"Unjailed {member.mention} and restored roles. (Case #{case_id})")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        _, appeal_channel_id = await self._get_jail_config(message.guild.id)
        if appeal_channel_id is None or message.channel.id != appeal_channel_id:
            return

        key = (message.guild.id, message.author.id)
        history = self.recent_messages.get(key, [])
        history.append(message.content.strip().lower())
        history = history[-3:]
        self.recent_messages[key] = history

        if len(history) == 3 and len(set(history)) == 1:
            try:
                await message.channel.set_permissions(
                    message.author, send_messages=False, reason="Spam: repeated identical messages"
                )
                await message.channel.send(
                    f"{message.author.mention} has been permanently blocked from this channel for spamming. "
                    f"A staff member can lift this with `~unjail`."
                )
            except discord.Forbidden:
                pass

    @commands.command(name="warn")
    @is_top_tier()
    async def warn(self, ctx, members: commands.Greedy[discord.Member], *, reason: str = "No reason provided"):
        """Warn one or more members. Antinuke owner / server owner / bot owner only. Example: ~warn @user1 @user2 spamming"""
        if not members:
            await send_temp(ctx, "Mention at least one member.")
            return
        names = ", ".join(m.mention for m in members)

        case_ids = []
        for member in members:
            case_id = await log_case(self.bot, ctx.guild, "warn", ctx.author, member, reason)
            case_ids.append(case_id)
            try:
                await member.send(f"You were warned in **{ctx.guild.name}**: {reason}")
            except discord.Forbidden:
                pass

        cases = ", ".join(f"#{c}" for c in case_ids)
        await send_temp(ctx, f"Warned: {names} — {reason} (Cases {cases})", allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="masskick", aliases=["mk"])
    @is_top_tier()
    async def masskick(self, ctx, members: commands.Greedy[discord.Member], *, reason: str = "No reason provided"):
        """Kick multiple members at once. Antinuke owner / server owner / bot owner only."""
        if not members:
            await send_temp(ctx, "Mention at least one member.")
            return
        names = ", ".join(m.mention for m in members)
        if not await ask_confirm(ctx, f"⚠️ Kick {len(members)} member(s): {names}? Reason: {reason}"):
            await send_temp(ctx, "Cancelled.")
            return
        if not await an.check_and_track(self.bot, ctx, "kick", "Mass kicking"):
            return

        results = []
        for member in members:
            try:
                await member.kick(reason=reason)
                case_id = await log_case(self.bot, ctx.guild, "kick", ctx.author, member, reason)
                results.append(f"{member.mention}: kicked (Case #{case_id})")
            except discord.Forbidden:
                results.append(f"{member.mention}: failed (missing permissions)")

        await send_temp(ctx, "\n".join(results), allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="massban", aliases=["mb"])
    @is_top_tier()
    async def massban(self, ctx, members: commands.Greedy[discord.Member], *, reason: str = "No reason provided"):
        """Ban multiple members at once. Antinuke owner / server owner / bot owner only."""
        if not members:
            await send_temp(ctx, "Mention at least one member.")
            return
        names = ", ".join(m.mention for m in members)
        if not await ask_confirm(ctx, f"⚠️ Ban {len(members)} member(s): {names}? Reason: {reason}"):
            await send_temp(ctx, "Cancelled.")
            return
        if not await an.check_and_track(self.bot, ctx, "ban", "Mass banning"):
            return

        results = []
        for member in members:
            try:
                await member.ban(reason=reason)
                case_id = await log_case(self.bot, ctx.guild, "ban", ctx.author, member, reason)
                results.append(f"{member.mention}: banned (Case #{case_id})")
            except discord.Forbidden:
                results.append(f"{member.mention}: failed (missing permissions)")

        await send_temp(ctx, "\n".join(results), allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="massjail", aliases=["mj"])
    @is_top_tier()
    async def massjail(self, ctx, members: commands.Greedy[discord.Member], *, reason: str = "No reason provided"):
        """Jail multiple members at once. Antinuke owner / server owner / bot owner only."""
        if not members:
            await send_temp(ctx, "Mention at least one member.")
            return

        jail_role_id, _ = await self._get_jail_config(ctx.guild.id)
        jail_role = ctx.guild.get_role(jail_role_id) if jail_role_id else None
        if jail_role is None:
            await send_temp(ctx, "Jail isn't set up yet — run `~jailsetup` first.")
            return

        results = []
        for member in members:
            try:
                roles_to_remove = [
                    role for role in member.roles
                    if not role.is_default() and not role.managed and role < ctx.guild.me.top_role
                ]
                role_ids_str = ",".join(str(r.id) for r in roles_to_remove)
                await self.bot.db.execute(
                    """
                    INSERT INTO jailed_user_roles (guild_id, user_id, role_ids)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET role_ids = excluded.role_ids
                    """,
                    (ctx.guild.id, member.id, role_ids_str)
                )

                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason=f"Mass Jailed: {reason}")
                await member.add_roles(jail_role, reason=f"Mass Jailed: {reason}")

                await self.bot.db.execute(
                    """
                    INSERT INTO jail_appeals (guild_id, user_id, has_pending_appeal)
                    VALUES (?, ?, 0)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET has_pending_appeal = 0
                    """,
                    (ctx.guild.id, member.id),
                )
                self.recent_messages.pop((ctx.guild.id, member.id), None)
                case_id = await log_case(self.bot, ctx.guild, "jail", ctx.author, member, reason)
                results.append(f"{member.mention}: jailed and stripped roles (Case #{case_id})")
            except discord.Forbidden:
                results.append(f"{member.mention}: failed (missing permissions)")

        await send_temp(ctx, "\n".join(results), allowed_mentions=discord.AllowedMentions.none())

async def setup(bot):
    await bot.add_cog(Moderation(bot))
