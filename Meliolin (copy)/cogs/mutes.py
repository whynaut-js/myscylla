import discord
from discord.ext import commands
from utils.checks import is_server_owner
from utils.permissions import has_botperm
from utils.modlog import log_case
from utils.setup_helpers import ask_role

MUTE_TYPES = {
    "text": {
        "role_col": "text_mute_role_id",
        "role_name": "Text Mute",
        "overwrite": {
            "send_messages": False,
            "send_messages_in_threads": False,
            "create_public_threads": False,
            "create_private_threads": False,
        },
    },
    "voice": {
        "role_col": "voice_mute_role_id",
        "role_name": "Voice Mute",
        "overwrite": {"speak": False, "stream": False},
    },
    "media": {
        "role_col": "media_mute_role_id",
        "role_name": "Media Mute",
        "overwrite": {"attach_files": False, "embed_links": False},
    },
    "reaction": {
        "role_col": "reaction_mute_role_id",
        "role_name": "Reaction Mute",
        "overwrite": {"add_reactions": False},
    },
}

class Mutes(commands.Cog):
    """Role-based mutes — separate Text, Voice, Media, and Reaction mute roles."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # Runs once when the cog loads (at every startup/restart) — so the
        # mute-role DB columns exist BEFORE anyone ever runs ~mute, instead
        # of only getting created the first time ~mutesetup happens to run.
        await self._ensure_columns()

    async def _ensure_columns(self):
        for info in MUTE_TYPES.values():
            try:
                await self.bot.db.execute(f"ALTER TABLE guild_config ADD COLUMN {info['role_col']} INTEGER")
            except Exception:
                pass

    async def _get_role_id(self, guild_id, mute_type):
        col = MUTE_TYPES[mute_type]["role_col"]
        row = await self.bot.db.fetchone(f"SELECT {col} FROM guild_config WHERE guild_id = ?", (guild_id,))
        return row[0] if row and row[0] else None

    @commands.command(name="mutesetup", aliases=["mset"])
    @is_server_owner()
    async def mutesetup(self, ctx):
        """One-time setup: creates (or adopts existing) Text, Voice, Media, and Reaction mute roles."""
        await self._ensure_columns()

        created = []
        adopted = []
        for mute_type, info in MUTE_TYPES.items():
            existing_id = await self._get_role_id(ctx.guild.id, mute_type)
            if existing_id and ctx.guild.get_role(existing_id):
                continue

            role = discord.utils.get(ctx.guild.roles, name=info["role_name"]) or await ask_role(ctx, info["role_name"])
            if role:
                adopted.append(role.mention)
            else:
                role = await ctx.guild.create_role(
                    name=info["role_name"], permissions=discord.Permissions.none(),
                    reason="Mute system setup",
                )
                for channel in ctx.guild.channels:
                    try:
                        overwrite = channel.overwrites_for(role)
                        for perm, value in info["overwrite"].items():
                            if hasattr(overwrite, perm):
                                setattr(overwrite, perm, value)
                        await channel.set_permissions(role, overwrite=overwrite, reason="Mute system setup")
                    except discord.Forbidden:
                        pass
                created.append(role.mention)

            await self.bot.db.execute(
                f"""
                INSERT INTO guild_config (guild_id, {info['role_col']})
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET {info['role_col']} = excluded.{info['role_col']}
                """,
                (ctx.guild.id, role.id),
            )

        if not created and not adopted:
            await ctx.send("Mute roles are already set up in this server.")
            return

        parts = []
        if created:
            parts.append(f"Created: {', '.join(created)}")
        if adopted:
            parts.append(f"Adopted existing: {', '.join(adopted)}")
        await ctx.send(" | ".join(parts))

    async def _apply_mute(self, ctx, member, mute_type, reason):
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "mute"):
            await ctx.send("You don't have permission to mute.")
            return

        role_id = await self._get_role_id(ctx.guild.id, mute_type)
        role = ctx.guild.get_role(role_id) if role_id else None
        if role is None:
            await ctx.send("Mute roles aren't set up yet — run `~mutesetup` first.")
            return

        await member.add_roles(role, reason=reason)
        case_id = await log_case(self.bot, ctx.guild, f"{mute_type}mute", ctx.author, member, reason)
        await ctx.send(f"{MUTE_TYPES[mute_type]['role_name']} applied to {member.mention} — {reason} (Case #{case_id})")

    async def _remove_mute(self, ctx, member, mute_type, reason):
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "mute"):
            await ctx.send("You don't have permission to unmute.")
            return

        role_id = await self._get_role_id(ctx.guild.id, mute_type)
        role = ctx.guild.get_role(role_id) if role_id else None
        if role and role in member.roles:
            await member.remove_roles(role, reason=reason)

        case_id = await log_case(self.bot, ctx.guild, f"un{mute_type}mute", ctx.author, member, reason)
        await ctx.send(f"{MUTE_TYPES[mute_type]['role_name']} removed from {member.mention}. (Case #{case_id})")

    @commands.command(name="mute", aliases=["m"])
    async def mute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Apply the Text Mute role. Example: ~mute @user spamming"""
        await self._apply_mute(ctx, member, "text", reason)

    @commands.command(name="unmute", aliases=["um"])
    async def unmute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Remove the Text Mute role."""
        await self._remove_mute(ctx, member, "text", reason)

    @commands.command(name="voicemute", aliases=["vmute", "vm"])
    async def voicemute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Apply the Voice Mute role."""
        await self._apply_mute(ctx, member, "voice", reason)

    @commands.command(name="unvoicemute", aliases=["unvmute", "uvm"])
    async def unvoicemute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Remove the Voice Mute role."""
        await self._remove_mute(ctx, member, "voice", reason)

    @commands.command(name="mediamute", aliases=["mmute", "mm"])
    async def mediamute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Apply the Media Mute role."""
        await self._apply_mute(ctx, member, "media", reason)

    @commands.command(name="unmediamute", aliases=["unmmute", "umm"])
    async def unmediamute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Remove the Media Mute role."""
        await self._remove_mute(ctx, member, "media", reason)

    @commands.command(name="reactionmute", aliases=["rmute", "rem"])
    async def reactionmute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Apply the Reaction Mute role."""
        await self._apply_mute(ctx, member, "reaction", reason)

    @commands.command(name="unreactionmute", aliases=["unrmute", "urem"])
    async def unreactionmute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Remove the Reaction Mute role."""
        await self._remove_mute(ctx, member, "reaction", reason)

async def setup(bot):
    await bot.add_cog(Mutes(bot))
