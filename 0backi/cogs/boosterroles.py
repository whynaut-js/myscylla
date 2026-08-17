import discord
from discord.ext import commands
from utils.colors import parse_hex

class BoosterRoles(commands.Cog):
    """Custom personal roles for server boosters."""

    def __init__(self, bot):
        self.bot = bot

    async def _get_own_role(self, ctx):
        row = await self.bot.db.fetchone(
            "SELECT role_id FROM booster_roles WHERE guild_id = ? AND owner_id = ?",
            (ctx.guild.id, ctx.author.id),
        )
        if not row:
            return None
        return ctx.guild.get_role(row[0])

    async def _reposition_all(self, ctx):
        row = await self.bot.db.fetchone(
            "SELECT booster_top_divider_id, booster_bottom_divider_id FROM guild_config WHERE guild_id = ?",
            (ctx.guild.id,),
        )
        top = ctx.guild.get_role(row[0]) if row and row[0] else None
        bottom = ctx.guild.get_role(row[1]) if row and row[1] else None

        if row and (row[0] or row[1]) and (top is None or bottom is None):
            return

        if top is None or bottom is None:
            bottom = await ctx.guild.create_role(
                name="⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯", permissions=discord.Permissions.none(),
                reason="Booster role divider (bottom)",
            )
            top = await ctx.guild.create_role(
                name="⎯⎯⎯ BOOSTER ROLES ⎯⎯⎯", permissions=discord.Permissions.none(),
                reason="Booster role divider (top)",
            )
            await self.bot.db.execute(
                """
                INSERT INTO guild_config (guild_id, booster_top_divider_id, booster_bottom_divider_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET booster_top_divider_id = excluded.booster_top_divider_id,
                                                     booster_bottom_divider_id = excluded.booster_bottom_divider_id
                """,
                (ctx.guild.id, top.id, bottom.id),
            )

        rows = await self.bot.db.fetchall(
            "SELECT role_id FROM booster_roles WHERE guild_id = ?", (ctx.guild.id,)
        )
        role_objs = [ctx.guild.get_role(r[0]) for r in rows if ctx.guild.get_role(r[0])]

        positions = {}
        pos = bottom.position + 1
        for r in role_objs:
            positions[r] = pos
            pos += 1
        positions[top] = pos

        try:
            await ctx.guild.edit_role_positions(positions=positions)
        except discord.HTTPException:
            pass

    @commands.group(invoke_without_command=True, aliases=["brole"])
    async def boosterrole(self, ctx):
        """Manage your personal booster role."""
        await ctx.send(
            "**Booster role commands (boosters only):**\n"
            "`~brole create <name>` (`~brole c`)\n"
            "`~brole rename <new name>` (`~brole rn`)\n"
            "`~brole color <hex>` (`~brole col`)\n"
            "`~brole gradient <hex1> <hex2> [hex3]` (`~brole g`)\n"
            "`~brole icon <emoji or attach an image>`\n"
            "`~brole share <@user>` (`~brole s`) / `~brole unshare <@user>` (`~brole us`)\n"
            "`~brole delete` (`~brole d`)"
        )

    @boosterrole.command(name="create", aliases=["c"])
    async def brole_create(self, ctx, *, name: str):
        """Create your personal booster role."""
        if ctx.author.premium_since is None:
            await ctx.send("Only server boosters can create a booster role.")
            return
        if await self._get_own_role(ctx):
            await ctx.send("You already have a booster role — use `~brole rename/color/etc` to edit it.")
            return

        role = await ctx.guild.create_role(
            name=name, permissions=discord.Permissions.none(), reason=f"Booster role for {ctx.author}"
        )
        await ctx.author.add_roles(role, reason="Booster role")
        await self.bot.db.execute(
            "INSERT INTO booster_roles (guild_id, owner_id, role_id) VALUES (?, ?, ?)",
            (ctx.guild.id, ctx.author.id, role.id),
        )
        await self._reposition_all(ctx)
        await ctx.send(f"Created your booster role {role.mention}!")

    @boosterrole.command(name="rename", aliases=["rn"])
    async def brole_rename(self, ctx, *, new_name: str):
        """Rename your booster role."""
        role = await self._get_own_role(ctx)
        if role is None:
            await ctx.send("You don't have a booster role yet — use `~brole create <name>`.")
            return
        await role.edit(name=new_name)
        await ctx.send(f"Renamed your booster role to `{new_name}`.")

    @boosterrole.command(name="color", aliases=["col"])
    async def brole_color(self, ctx, hex_color: str):
        """Set your booster role's color."""
        role = await self._get_own_role(ctx)
        if role is None:
            await ctx.send("You don't have a booster role yet — use `~brole create <name>`.")
            return
        colour = parse_hex(hex_color)
        if colour is None:
            await ctx.send("Invalid hex color. Example: `ff0000`.")
            return
        await role.edit(colour=colour)
        await ctx.send(f"Set your booster role's color to `#{hex_color.lstrip('#')}`.")

    @boosterrole.command(name="gradient", aliases=["g"])
    async def brole_gradient(self, ctx, hex1: str, hex2: str, hex3: str = None):
        """Set your booster role's gradient (requires server boost level 2+)."""
        role = await self._get_own_role(ctx)
        if role is None:
            await ctx.send("You don't have a booster role yet — use `~brole create <name>`.")
            return
        c1, c2 = parse_hex(hex1), parse_hex(hex2)
        c3 = parse_hex(hex3) if hex3 else None
        if c1 is None or c2 is None or (hex3 and c3 is None):
            await ctx.send("Invalid hex color(s).")
            return
        try:
            kwargs = {"colour": c1, "secondary_colour": c2}
            if c3:
                kwargs["tertiary_colour"] = c3
            await role.edit(**kwargs)
            await ctx.send("Gradient set on your booster role.")
        except (discord.HTTPException, TypeError):
            await ctx.send("Couldn't set gradient — this server may need a higher boost level.")

    @boosterrole.command(name="icon")
    async def brole_icon(self, ctx, icon: str = None):
        """Set your booster role's icon (emoji or attached image). Requires boost level 2+."""
        role = await self._get_own_role(ctx)
        if role is None:
            await ctx.send("You don't have a booster role yet — use `~brole create <name>`.")
            return
        try:
            if ctx.message.attachments:
                icon_bytes = await ctx.message.attachments[0].read()
                await role.edit(display_icon=icon_bytes)
            elif icon:
                await role.edit(display_icon=icon)
            else:
                await ctx.send("Provide an emoji or attach an image.")
                return
            await ctx.send("Icon set on your booster role.")
        except discord.HTTPException:
            await ctx.send("Couldn't set icon — this server may need a higher boost level.")

    @boosterrole.command(name="share", aliases=["s"])
    async def brole_share(self, ctx, member: discord.Member):
        """Give another member your booster role."""
        role = await self._get_own_role(ctx)
        if role is None:
            await ctx.send("You don't have a booster role yet — use `~brole create <name>`.")
            return
        await member.add_roles(role, reason=f"Shared by {ctx.author}")
        await ctx.send(f"Shared your booster role with {member.mention}.")

    @boosterrole.command(name="unshare", aliases=["us"])
    async def brole_unshare(self, ctx, member: discord.Member):
        """Remove your booster role from someone you shared it with."""
        role = await self._get_own_role(ctx)
        if role is None:
            await ctx.send("You don't have a booster role yet.")
            return
        await member.remove_roles(role, reason=f"Unshared by {ctx.author}")
        await ctx.send(f"Removed your booster role from {member.mention}.")

    @boosterrole.command(name="delete", aliases=["d"])
    async def brole_delete(self, ctx):
        """Delete your booster role entirely."""
        role = await self._get_own_role(ctx)
        if role is None:
            await ctx.send("You don't have a booster role.")
            return
        await role.delete(reason=f"Deleted by {ctx.author}")
        await self.bot.db.execute(
            "DELETE FROM booster_roles WHERE guild_id = ? AND owner_id = ?",
            (ctx.guild.id, ctx.author.id),
        )
        await ctx.send("Booster role deleted.")

async def setup(bot):
    await bot.add_cog(BoosterRoles(bot))
