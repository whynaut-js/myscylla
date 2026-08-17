import discord
from discord.ext import commands

class Invites(commands.Cog):
    """Tracks which invite link was used for each join, so we can later
    answer 'who invited this person'. Only works for joins that happen
    after this cog is loaded — can't retroactively know past joins."""

    def __init__(self, bot):
        self.bot = bot
        self.invite_cache = {}  # {guild_id: {code: uses}}

    async def _cache_guild_invites(self, guild: discord.Guild):
        try:
            invites = await guild.invites()
            self.invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
        except discord.Forbidden:
            self.invite_cache[guild.id] = {}

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self._cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self._cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        self.invite_cache.setdefault(invite.guild.id, {})[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        self.invite_cache.get(invite.guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        before = self.invite_cache.get(guild.id, {})

        try:
            after_invites = await guild.invites()
        except discord.Forbidden:
            return

        after = {inv.code: inv.uses for inv in after_invites}
        used_code = None
        inviter_id = None

        for inv in after_invites:
            prev_uses = before.get(inv.code, 0)
            if inv.uses is not None and inv.uses > prev_uses:
                used_code = inv.code
                inviter_id = inv.inviter.id if inv.inviter else None
                break

        if used_code is None:
            try:
                vanity = await guild.vanity_invite()
                if vanity:
                    used_code = vanity.code
            except (discord.Forbidden, discord.HTTPException):
                pass

        self.invite_cache[guild.id] = after

        await self.bot.db.execute(
            """
            INSERT INTO join_invites (guild_id, user_id, inviter_id, invite_code, joined_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                inviter_id = excluded.inviter_id,
                invite_code = excluded.invite_code,
                joined_at = excluded.joined_at
            """,
            (guild.id, member.id, inviter_id, used_code, discord.utils.utcnow().isoformat()),
        )

async def setup(bot):
    await bot.add_cog(Invites(bot))
