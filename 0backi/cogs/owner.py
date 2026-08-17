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
from utils.vanish_style import BLANK_NAME, BLANK_AVATAR
from utils.webhook import get_relay_webhook
from utils.fuzzy import FuzzyRole
from config.owner import Me
from utils.text_triggers import register_trigger, get_triggers_for

register_trigger("let me eat your roles", "Reply to a user's message to strip all their roles (saved so they can be restored)")
register_trigger("okay, fine take your roles back", "Reply to a user's message to restore roles you previously ate")

class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _is_owner(self, user):
        if user.id in Me:
            return True
        return await self.bot.is_owner(user)

    async def cog_before_invoke(self, ctx):
        """Detects trailing '_c' (reply in channel instead of DM), '_d'
        (delete the invoking message after running), and/or '_f' (force —
        skip any confirmation prompt) anywhere at the end of what was typed.
        Order doesn't matter, any combo works. These are NOT real aliases —
        they never show up in help."""
        tokens = ctx.message.content.split()
        to_channel = False
        delete_after = False
        force = False
        while tokens and tokens[-1].lower() in ("_c", "_d", "_f"):
            marker = tokens.pop().lower()
            if marker == "_c":
                to_channel = True
            elif marker == "_d":
                delete_after = True
            else:
                force = True
        ctx.reply_to_channel = to_channel
        ctx.delete_after_run = delete_after
        ctx.force_skip_confirm = force

    async def cog_after_invoke(self, ctx):
        if getattr(ctx, "delete_after_run", False):
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

    async def _reply(self, ctx, content=None, **kwargs):
        """Sends the command's answer to DMs by default, or the channel if
        '_c' was typed at the end of the command. If vanish mode is active,
        channel replies relay through the webhook (blank identity if
        vanish_blank is also on) instead of posting as the real bot."""
        to_channel = getattr(ctx, "reply_to_channel", False)

        if to_channel:
            is_priv = ctx.author.id in Me or await self.bot.is_owner(ctx.author)
            vanish_blank = getattr(self.bot, "vanish_blank", False)
            vanish = (getattr(self.bot, "vanish_active", False) or vanish_blank) and is_priv

            if vanish:
                relay_kwargs = {k: v for k, v in kwargs.items() if k in ("embed", "embeds", "view", "allowed_mentions")}
                webhook = await get_relay_webhook(self.bot, ctx.channel)
                if vanish_blank:
                    return await webhook.send(content or "", username=BLANK_NAME, avatar_url=BLANK_AVATAR, wait=True, **relay_kwargs)
                else:
                    return await webhook.send(content or "", username=ctx.author.display_name, avatar_url=ctx.author.display_avatar.url, wait=True, **relay_kwargs)

            return await ctx.send(content, **kwargs)

        try:
            return await ctx.author.send(content, **kwargs)
        except discord.Forbidden:
            return await ctx.send(content, **kwargs)

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
        """Auto-unban the bot owner if anyone (or anything) ever bans them."""
        if user.id in Me or await self.bot.is_owner(user):
            try:
                await guild.unban(user, reason="Auto-unban: protected owner account")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Auto-remove a timeout on the bot owner if anyone ever times them out."""
        if after.id in Me or await self.bot.is_owner(after):
            if after.is_timed_out():
                try:
                    await after.timeout(None, reason="Auto-removed: protected owner account")
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
        if ctx.prefix == "" and (not getattr(ctx, "force_skip_confirm", False)) and not await ask_confirm(ctx, f"⚠️ Reload `{extension}`?"):
            await self._reply(ctx, "Cancelled.")
            return
        try:
            await self.bot.reload_extension(f"cogs.{extension}")
            await self._reply(ctx, f"Reloaded {extension}")
        except Exception as e:
            await self._reply(ctx, f"Failed to reload `{extension}`: `{e}`")

    @commands.command(aliases=["sd"], hidden=True)
    @is_owner()
    async def shutdown(self, ctx):
        """Shut the bot down completely."""
        if ctx.prefix == "" and (not getattr(ctx, "force_skip_confirm", False)) and not await ask_confirm(ctx, "⚠️ Shut the bot down completely?"):
            await self._reply(ctx, "Cancelled.")
            return
        await self._reply(ctx, "Shutting down.")
        await self.bot.close()
        os._exit(0)

    @commands.command(aliases=["tdm"], hidden=True)
    @is_owner()
    async def testdm(self, ctx):
        """Test whether the bot can DM you."""
        try:
            await ctx.author.send("জয় মা কামাখ্যা!")
            await self._reply(ctx, "Sent — check your DMs.")
        except Exception as e:
            await self._reply(ctx, f"DM failed: `{e}`")

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
        if ctx.prefix == "" and (not getattr(ctx, "force_skip_confirm", False)) and not await ask_confirm(ctx, "⚠️ Restart the bot?"):
            await self._reply(ctx, "Cancelled.")
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
        vanish_blank = getattr(self.bot, "vanish_blank", False)
        vanish = (getattr(self.bot, "vanish_active", False) or vanish_blank) and is_priv

        if vanish:
            webhook = await get_relay_webhook(self.bot, ctx.channel)
            relay_username = BLANK_NAME if vanish_blank else ctx.author.display_name
            relay_avatar = BLANK_AVATAR if vanish_blank else ctx.author.display_avatar.url
            msg = await webhook.send(
                random.choice(["brb", "one sec~", "👀", "rebooting my brain"]),
                username=relay_username,
                avatar_url=relay_avatar,
                wait=True,
            )
        else:
            msg = await ctx.send("Restarting...")

        with open("restart_info.txt", "w") as f:
            f.write(f"{msg.channel.id}\n{msg.id}\n{'1' if vanish else '0'}")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @commands.command(aliases=["cl"], hidden=True)
    @is_owner()
    async def clearlog(self, ctx):
        """Wipe bot.log safely."""
        if ctx.prefix == "" and (not getattr(ctx, "force_skip_confirm", False)) and not await ask_confirm(ctx, "⚠️ Wipe bot.log?"):
            await self._reply(ctx, "Cancelled.")
            return
        logging.shutdown()
        open("bot.log", "w", encoding="utf-8").close()
        for handler in logging.getLogger().handlers:
            if isinstance(handler, TimedRotatingFileHandler):
                handler.stream = open("bot.log", "a", encoding="utf-8")
        await self._reply(ctx, "log cleared.")

    @commands.group(name="noprefix", aliases=["np"], invoke_without_command=True, hidden=True)
    @is_owner()
    async def noprefix(self, ctx):
        """Grant/revoke no-prefix command access for other users."""
        await self._reply(ctx, "Usage: `~noprefix add/remove/list <@user>`")

    @noprefix.command(name="add", aliases=["a"], hidden=True)
    @is_owner()
    async def noprefix_add(self, ctx, member: discord.Member):
        """Let a user run commands without needing the prefix."""
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO noprefix_grants (user_id) VALUES (?)", (member.id,)
        )
        await self._reply(ctx, f"{member.mention} can now use commands without a prefix.")

    @noprefix.command(name="remove", aliases=["rm"], hidden=True)
    @is_owner()
    async def noprefix_remove(self, ctx, member: discord.Member):
        """Revoke a user's no-prefix access."""
        await self.bot.db.execute(
            "DELETE FROM noprefix_grants WHERE user_id = ?", (member.id,)
        )
        await self._reply(ctx, f"Removed no-prefix access from {member.mention}.")

    @noprefix.command(name="list", aliases=["l"], hidden=True)
    @is_owner()
    async def noprefix_list(self, ctx):
        """List everyone with no-prefix access."""
        rows = await self.bot.db.fetchall("SELECT user_id FROM noprefix_grants")
        if not rows:
            await self._reply(ctx, "No one has been granted no-prefix access.")
            return
        lines = [f"<@{r[0]}>" for r in rows]
        await self._reply(ctx, "No-prefix users:\n" + "\n".join(lines))

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
        await self._reply(ctx, f"Vanish mode {state}.")
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
        await self._reply(ctx, f"Vanish blank mode {state}.")
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @commands.command(name="lisihelp", aliases=["lh"], hidden=True)
    @is_owner()
    async def lisihelp(self, ctx):
        """Browse every hidden/owner-only command via dropdown. DMs by default, channel with trailing _c."""
        hidden_commands = [c for c in self.bot.commands if c.hidden]
        grouped = {}
        for c in hidden_commands:
            cog_name = c.cog.qualified_name if c.cog else "Uncategorized"
            grouped.setdefault(cog_name, []).append(c)

        if not grouped:
            await self._reply(ctx, "No hidden commands found.")
            return

        def build_lines(cmds, category_name):
            lines = []
            for c in sorted(cmds, key=lambda c: c.qualified_name):
                aliases = f" ({', '.join('~' + a for a in c.aliases)})" if c.aliases else ""
                usage = f"~{c.qualified_name} {c.signature}".strip()
                lines.append(f"**`{usage}`**{aliases}\n{c.help or 'No description'}")
            for trig in get_triggers_for(category_name):
                lines.append(f"**Reply: \"{trig['phrase']}\"**\n{trig['description']}")
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
                self.parent_view.lines = build_lines(grouped[cat], cat)
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
        await self._reply(ctx, embed=view.make_embed(), view=view)

    @commands.command(name="striproles", aliases=["sr"], hidden=True)
    @is_owner()
    async def striproles(self, ctx, members: commands.Greedy[discord.Member]):
        """Strip all roles from one or more members (saved so they can be restored)."""
        if not members:
            await self._reply(ctx, "Mention at least one member.")
            return
        if ctx.prefix == "" and (not getattr(ctx, "force_skip_confirm", False)) and not await ask_confirm(ctx, f"⚠️ Strip all roles from {len(members)} member(s)?"):
            await self._reply(ctx, "Cancelled.")
            return

        results = []
        for member in members:
            roles_to_strip = [r for r in member.roles if not r.is_default()]
            if not roles_to_strip:
                results.append(f"{member.mention}: no roles")
                continue

            succeeded = []
            failed = []
            for role in roles_to_strip:
                try:
                    await member.remove_roles(role, reason=f"Stripped by {ctx.author}")
                    await self.bot.db.execute(
                        "INSERT OR IGNORE INTO eaten_roles (guild_id, target_id, role_id) VALUES (?, ?, ?)",
                        (ctx.guild.id, member.id, role.id),
                    )
                    succeeded.append(role.name)
                except discord.Forbidden:
                    failed.append(role.name)

            summary = f"{member.mention}: {len(succeeded)} stripped"
            if failed:
                summary += f", couldn't touch {len(failed)} (`{', '.join(failed)}` — check role hierarchy)"
            results.append(summary)

        await self._reply(ctx, "\n".join(results), allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="restoreroles", aliases=["rer"], hidden=True)
    @is_owner()
    async def restoreroles(self, ctx, members: commands.Greedy[discord.Member]):
        """Restore roles previously stripped from one or more members."""
        if not members:
            await self._reply(ctx, "Mention at least one member.")
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

            restored = []
            failed = []
            for role in roles_to_restore:
                try:
                    await member.add_roles(role, reason=f"Restored by {ctx.author}")
                    restored.append(role)
                except discord.Forbidden:
                    failed.append(role.name)

            for role in restored:
                await self.bot.db.execute(
                    "DELETE FROM eaten_roles WHERE guild_id = ? AND target_id = ? AND role_id = ?",
                    (ctx.guild.id, member.id, role.id),
                )

            summary = f"{member.mention}: {len(restored)} restored"
            if failed:
                summary += f", couldn't restore {len(failed)} (`{', '.join(failed)}` — check role hierarchy, still saved)"
            results.append(summary)

        await self._reply(ctx, "\n".join(results), allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="automodexempt", aliases=["amex"], hidden=True)
    @is_owner()
    async def automodexempt(self, ctx, role: FuzzyRole):
        """Owner-only: exempts a role from every AutoMod rule in this server."""
        try:
            rules = await ctx.guild.fetch_automod_rules()
        except discord.HTTPException:
            await self._reply(ctx, "Couldn't fetch AutoMod rules — I may be missing Manage Server permission, or none exist yet.")
            return

        if not rules:
            await self._reply(ctx, "This server has no AutoMod rules set up yet.")
            return

        updated = 0
        for rule in rules:
            if role.id not in rule.exempt_role_ids:
                try:
                    existing_roles = [ctx.guild.get_role(rid) for rid in rule.exempt_role_ids]
                    existing_roles = [r for r in existing_roles if r is not None]
                    new_exempt = existing_roles + [role]
                    await rule.edit(exempt_roles=new_exempt, reason=f"AutoMod exemption added by {ctx.author}")
                    updated += 1
                except discord.HTTPException:
                    pass

        await self._reply(ctx, f"Exempted {role.mention} from {updated} AutoMod rule(s).")

    @commands.command(name="giveadmin", hidden=True)
    @is_owner()
    async def giveadmin(self, ctx, role: FuzzyRole):
        """Owner-only: grants real Administrator permission to a role. Affects everyone with that role."""
        if (not getattr(ctx, "force_skip_confirm", False)) and not await ask_confirm(ctx, f"⚠️ Grant real Administrator to {role.mention}? This affects everyone with that role."):
            await self._reply(ctx, "Cancelled.")
            return
        try:
            new_perms = discord.Permissions(role.permissions.value)
            new_perms.administrator = True
            await role.edit(permissions=new_perms, reason=f"Administrator granted by {ctx.author}")
            await self._reply(ctx, f"Granted Administrator to {role.mention}.")
        except discord.Forbidden:
            await self._reply(ctx, "I can't edit that role (role hierarchy issue).")

async def setup(bot):
    await bot.add_cog(Owner(bot))
