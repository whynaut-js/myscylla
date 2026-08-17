import discord
from discord.ext import commands
from utils.permissions import has_botperm
from utils.colors import parse_hex
from utils.fuzzy import FuzzyRole
from utils.pagination import PaginatorView
from utils.confirm import ask_confirm
from utils import antinuke as an

class Roles(commands.Cog):
    """General role management — create, rename, recolor, gradient, icon, add/remove/delete, list."""

    def __init__(self, bot):
        self.bot = bot

    async def _check(self, ctx):
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "manage_roles"):
            await ctx.send("You don't have permission to manage roles.")
            return False
        return True

    async def _antinuke_check(self, ctx):
        from cogs.antinuke import antinuke_admin_check
        predicate = antinuke_admin_check().predicate
        try:
            return await predicate(ctx)
        except commands.CheckFailure:
            await ctx.send("Assigning/removing multiple roles at once requires antinuke admin or higher.")
            return False

    @commands.group(invoke_without_command=True, aliases=["role"])
    async def roles(self, ctx):
        """Manage server roles."""
        await ctx.send(
            "**Role commands** (nested `~role <sub>` or standalone shortcut):\n"
            "`~role create <name>` — `~rc`\n"
            "`~role delete <role>` — `~rd` (asks to confirm)\n"
            "`~role rename <role> <new name>` — `~rn`\n"
            "`~role color <role> <hex>` — `~rcol`\n"
            "`~role gradient <role> <hex1> <hex2> [hex3]` — `~rg`\n"
            "`~role icon <role> <emoji/attach image>` — `~ricon`\n"
            "`~role add <role> <@user1> [@user2 ...]` — `~ra`\n"
            "`~role remove <role> <@user1> [@user2 ...]` — `~rr`\n"
            "`~role all <role>` — `~rall`\n"
            "`~listroles` (`~lr`) — every role, paginated\n"
            "`~inrole <role>` (`~ir`) — everyone with that role, paginated\n\n"
            "Tip: role args accept a mention, ID, exact name, or a close-enough spelling."
        )

    @roles.command(name="create", aliases=["rc"])
    async def roles_create(self, ctx, *, name: str):
        """Create a new role."""
        if not await self._check(ctx):
            return
        role = await ctx.guild.create_role(name=name, reason=f"Created by {ctx.author}")
        await ctx.send(f"Created role {role.mention}.")

    @roles.command(name="delete", aliases=["rd"])
    async def roles_delete(self, ctx, role: FuzzyRole):
        """Delete a role entirely. Requires confirmation."""
        if not await self._check(ctx):
            return

        if not await ask_confirm(ctx, f"⚠️ Delete the role **{role.name}**? This **cannot** be undone."):
            await ctx.send("Cancelled.")
            return

        if not await an.check_and_track(self.bot, ctx, "role_delete", "Mass role deletion"):
            return

        name = role.name
        await role.delete(reason=f"Deleted by {ctx.author}")
        await ctx.send(f"Deleted role `{name}`.")

    @roles.command(name="rename", aliases=["rn"])
    async def roles_rename(self, ctx, role: FuzzyRole, *, new_name: str):
        """Rename an existing role."""
        if not await self._check(ctx):
            return
        old_name = role.name
        await role.edit(name=new_name, reason=f"Renamed by {ctx.author}")
        await ctx.send(f"Renamed `{old_name}` to `{new_name}`.")

    @roles.command(name="color", aliases=["rcol"])
    async def roles_color(self, ctx, role: FuzzyRole, hex_color: str):
        """Set a role's color. Example: ~role color Mods ff0000"""
        if not await self._check(ctx):
            return
        colour = parse_hex(hex_color)
        if colour is None:
            await ctx.send("Invalid hex color. Example: `ff0000` or `#ff0000`.")
            return
        await role.edit(colour=colour, reason=f"Recolored by {ctx.author}")
        await ctx.send(f"Set {role.mention}'s color to `#{hex_color.lstrip('#')}`.")

    @roles.command(name="gradient", aliases=["rg"])
    async def roles_gradient(self, ctx, role: FuzzyRole, hex1: str, hex2: str, hex3: str = None):
        """Set a role's gradient color (requires server boost level 2+). Example: ~role gradient VIP ff0000 0000ff"""
        if not await self._check(ctx):
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
            await role.edit(reason=f"Gradient set by {ctx.author}", **kwargs)
            await ctx.send(f"Gradient set on {role.mention}.")
        except (discord.HTTPException, TypeError):
            await ctx.send(
                "Couldn't set gradient — this server may not have enough boost level "
                "(needs Level 2+) or your discord.py version may not support it."
            )

    @roles.command(name="icon", aliases=["ricon"])
    async def roles_icon(self, ctx, role: FuzzyRole, icon: str = None):
        """Set a role's icon. Provide an emoji, or attach an image. Requires boost level 2+."""
        if not await self._check(ctx):
            return
        try:
            if ctx.message.attachments:
                icon_bytes = await ctx.message.attachments[0].read()
                await role.edit(display_icon=icon_bytes, reason=f"Icon set by {ctx.author}")
            elif icon:
                await role.edit(display_icon=icon, reason=f"Icon set by {ctx.author}")
            else:
                await ctx.send("Provide an emoji or attach an image.")
                return
            await ctx.send(f"Icon set on {role.mention}.")
        except discord.HTTPException:
            await ctx.send("Couldn't set icon — this server may not have enough boost level (needs Level 2+).")

    @roles.command(name="add", aliases=["ra"])
    async def roles_add(self, ctx, *, arg: str):
        """Add one or more roles to one or more members.
        Single role: ~role add Mods @user1 @user2
        Multiple roles: ~role add Mods, VIP | @user1 @user2"""
        if not await self._check(ctx):
            return

        if "|" in arg:
            roles_part, members_part = arg.split("|", 1)
        else:
            parts = arg.split(maxsplit=1)
            roles_part = parts[0] if parts else ""
            members_part = parts[1] if len(parts) > 1 else ""

        role_tokens = [t.strip() for t in roles_part.replace(",", " ").split() if t.strip()]
        roles = []
        for token in role_tokens:
            try:
                roles.append(await FuzzyRole().convert(ctx, token))
            except commands.BadArgument:
                await ctx.send(f"Couldn't find role `{token}` — skipping.")
        if not roles:
            await ctx.send("No valid role(s) found.")
            return

        if len(roles) > 1 and not await self._antinuke_check(ctx):
            return

        converter = commands.MemberConverter()
        members = []
        for token in members_part.split():
            try:
                members.append(await converter.convert(ctx, token))
            except commands.BadArgument:
                pass
        if not members:
            await ctx.send("Mention at least one member.")
            return

        for member in members:
            await member.add_roles(*roles, reason=f"Added by {ctx.author}")
        role_names = ", ".join(r.mention for r in roles)
        member_names = ", ".join(m.mention for m in members)
        await ctx.send(f"Added {role_names} to: {member_names}", allowed_mentions=discord.AllowedMentions.none())

    @roles.command(name="remove", aliases=["rr"])
    async def roles_remove(self, ctx, *, arg: str):
        """Remove one or more roles from one or more members.
        Single role: ~role remove Mods @user1 @user2
        Multiple roles: ~role remove Mods, VIP | @user1 @user2"""
        if not await self._check(ctx):
            return

        if "|" in arg:
            roles_part, members_part = arg.split("|", 1)
        else:
            parts = arg.split(maxsplit=1)
            roles_part = parts[0] if parts else ""
            members_part = parts[1] if len(parts) > 1 else ""

        role_tokens = [t.strip() for t in roles_part.replace(",", " ").split() if t.strip()]
        roles = []
        for token in role_tokens:
            try:
                roles.append(await FuzzyRole().convert(ctx, token))
            except commands.BadArgument:
                await ctx.send(f"Couldn't find role `{token}` — skipping.")
        if not roles:
            await ctx.send("No valid role(s) found.")
            return

        if len(roles) > 1 and not await self._antinuke_check(ctx):
            return

        converter = commands.MemberConverter()
        members = []
        for token in members_part.split():
            try:
                members.append(await converter.convert(ctx, token))
            except commands.BadArgument:
                pass
        if not members:
            await ctx.send("Mention at least one member.")
            return

        for member in members:
            await member.remove_roles(*roles, reason=f"Removed by {ctx.author}")
        role_names = ", ".join(r.mention for r in roles)
        member_names = ", ".join(m.mention for m in members)
        await ctx.send(f"Removed {role_names} from: {member_names}", allowed_mentions=discord.AllowedMentions.none())

    @roles.command(name="all", aliases=["rall"])
    async def roles_all(self, ctx, role: FuzzyRole):
        """Give a role to every member in the server."""
        if not await self._check(ctx):
            return
        status = await ctx.send(f"Adding {role.mention} to everyone — this may take a while on large servers...")
        added = 0
        failed = 0
        for member in ctx.guild.members:
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Mass-added by {ctx.author}")
                    added += 1
                except discord.HTTPException:
                    failed += 1
        await status.edit(content=f"Done. Added {role.mention} to {added} member(s), {failed} failed.")

    @commands.command(name="listroles", aliases=["lr"])
    async def listroles(self, ctx):
        """List every role in the server, paginated, without pinging any of them."""
        sorted_roles = sorted(ctx.guild.roles, key=lambda r: r.position, reverse=True)
        lines = [f"{r.mention} — {len(r.members)} member(s)" for r in sorted_roles if r.name != "@everyone"]
        if not lines:
            await ctx.send("No roles found.")
            return
        view = PaginatorView(lines, title=f"Roles in {ctx.guild.name}")
        await ctx.send(embed=view.make_embed(), view=view)

    @commands.command(name="inrole", aliases=["ir"])
    async def inrole(self, ctx, role: FuzzyRole):
        """List everyone with a specific role, paginated, without pinging them."""
        members = role.members
        if not members:
            await ctx.send(f"No one currently has {role.mention}.", allowed_mentions=discord.AllowedMentions.none())
            return
        lines = [f"{m.mention} ({m.display_name})" for m in members]
        view = PaginatorView(lines, title=f"Members in {role.name} ({len(members)})")
        await ctx.send(embed=view.make_embed(), view=view)

    # === Standalone flat shortcuts (no ~role prefix needed) ===

    @commands.command(name="rc")
    async def rc_flat(self, ctx, *, name: str):
        """Shortcut for ~role create."""
        await self.roles_create.callback(self, ctx, name=name)

    @commands.command(name="rd")
    async def rd_flat(self, ctx, role: FuzzyRole):
        """Shortcut for ~role delete."""
        await self.roles_delete.callback(self, ctx, role)

    @commands.command(name="rn")
    async def rn_flat(self, ctx, role: FuzzyRole, *, new_name: str):
        """Shortcut for ~role rename."""
        await self.roles_rename.callback(self, ctx, role, new_name=new_name)

    @commands.command(name="rcol")
    async def rcol_flat(self, ctx, role: FuzzyRole, hex_color: str):
        """Shortcut for ~role color."""
        await self.roles_color.callback(self, ctx, role, hex_color)

    @commands.command(name="rg")
    async def rg_flat(self, ctx, role: FuzzyRole, hex1: str, hex2: str, hex3: str = None):
        """Shortcut for ~role gradient."""
        await self.roles_gradient.callback(self, ctx, role, hex1, hex2, hex3)

    @commands.command(name="ricon")
    async def ricon_flat(self, ctx, role: FuzzyRole, icon: str = None):
        """Shortcut for ~role icon."""
        await self.roles_icon.callback(self, ctx, role, icon)

    @commands.command(name="ra")
    async def ra_flat(self, ctx, *, arg: str):
        """Shortcut for ~role add."""
        await self.roles_add.callback(self, ctx, arg=arg)

    @commands.command(name="rr")
    async def rr_flat(self, ctx, *, arg: str):
        """Shortcut for ~role remove."""
        await self.roles_remove.callback(self, ctx, arg=arg)

    @commands.command(name="rall")
    async def rall_flat(self, ctx, role: FuzzyRole):
        """Shortcut for ~role all."""
        await self.roles_all.callback(self, ctx, role)

async def setup(bot):
    await bot.add_cog(Roles(bot))
