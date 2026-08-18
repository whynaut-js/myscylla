import discord
from discord.ext import commands

EXCLUDED_COGS = {"Owner", "Help"}
EMBED_COLOR = discord.Color.from_rgb(88, 101, 242)

# Which category each cog belongs to. Matched case-insensitively against the
# cog's actual class name, so this survives minor capitalization differences.
# Anything not listed here falls into "extras" automatically — if something
# lands in the wrong bucket, just move its name to the right list below.
CATEGORIES = {
    "security":   {"label": "಄ Security",         "cogs": ["antinuke", "wipe", "botperms", "pingrole"]},
    "moderation": {"label": "🛡️ Moderation",       "cogs": ["moderation", "modlog", "mutes", "purge"]},
    "management": {"label": "𓏲 ๋࣭ Management",     "cogs": ["roles", "channels", "boosterroles", "serverconfig", "invites"]},
    "utilities":  {"label": "⚙ Utilities",         "cogs": ["latency", "snipe", "userinfo", "autosend", "nicknames"]},
    "media":      {"label": "🎬 Media",            "cogs": ["steal", "infocards"]},
    "extras":     {"label": "🎐 Extras",           "cogs": ["giveaway", "annoy", "mimic", "uwu"]},
}

def get_category_for(cog_name: str) -> str:
    lname = cog_name.lower()
    for key, info in CATEGORIES.items():
        if lname in info["cogs"]:
            return key
    return "extras"

def usage_line(c) -> str:
    return f"~{c.qualified_name} {c.signature}".strip()

def compact_module_summary(cog) -> str:
    """Short per-module listing for the category-level view — just names,
    aliases, and (for groups) subcommand names. No descriptions yet."""
    lines = []
    for cmd in sorted(cog.get_commands(), key=lambda c: c.name):
        if cmd.hidden:
            continue
        alias_txt = f" (`{'`, `'.join('~' + a for a in cmd.aliases)}`)" if cmd.aliases else ""
        if isinstance(cmd, commands.Group):
            subs = ", ".join(s.name for s in sorted(cmd.commands, key=lambda s: s.name) if not s.hidden)
            lines.append(f"`{cmd.qualified_name}`{alias_txt} *(subcommands: {subs})*" if subs else f"`{cmd.qualified_name}`{alias_txt}")
        else:
            lines.append(f"`{cmd.qualified_name}`{alias_txt}")
    return "\n".join(lines) if lines else "*No commands*"

def detailed_module_lines(cog):
    """Full usage + description (+ Example, if the docstring has one) per
    command, for the module-detail view."""
    lines = []
    for cmd in sorted(cog.get_commands(), key=lambda c: c.name):
        if cmd.hidden:
            continue
        aliases = f" ({', '.join('~' + a for a in cmd.aliases)})" if cmd.aliases else ""
        help_text = cmd.help or "No description"
        example = None
        if "Example:" in help_text:
            help_text, _, example = help_text.partition("Example:")
            help_text = help_text.strip()
            example = example.strip()

        entry = f"**`{usage_line(cmd)}`**{aliases}\n{help_text}"
        if example:
            entry += f"\n> Example: `{example}`"
        lines.append(entry)

        if isinstance(cmd, commands.Group):
            for sub in sorted(cmd.commands, key=lambda s: s.name):
                if sub.hidden:
                    continue
                sub_aliases = f" ({', '.join('~' + a for a in sub.aliases)})" if sub.aliases else ""
                sub_help = sub.help or "No description"
                sub_example = None
                if "Example:" in sub_help:
                    sub_help, _, sub_example = sub_help.partition("Example:")
                    sub_help = sub_help.strip()
                    sub_example = sub_example.strip()
                sub_entry = f"  ↳ **`{usage_line(sub)}`**{sub_aliases}\n     {sub_help}"
                if sub_example:
                    sub_entry += f"\n     > Example: `{sub_example}`"
                lines.append(sub_entry)
    return lines

class MainCategorySelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label=info["label"], value=key, description=f"{parent_view.category_counts.get(key, 0)} command(s)")
            for key, info in CATEGORIES.items() if parent_view.category_counts.get(key, 0) > 0
        ]
        super().__init__(placeholder="Select a main category...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.invoker_id:
            await interaction.response.send_message("This isn't your help menu — run `~help` yourself.", ephemeral=True)
            return
        self.parent_view.set_category(self.values[0])
        await interaction.response.edit_message(embed=self.parent_view.make_embed(), view=self.parent_view)

class ModuleSelect(discord.ui.Select):
    def __init__(self, parent_view, modules):
        self.parent_view = parent_view
        options = [discord.SelectOption(label=name) for name in modules]
        placeholder = f"Filter by subcategory in {parent_view.current_category_label}..."
        super().__init__(placeholder=placeholder[:150], options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.invoker_id:
            await interaction.response.send_message("This isn't your help menu — run `~help` yourself.", ephemeral=True)
            return
        self.parent_view.set_module(self.values[0])
        await interaction.response.edit_message(embed=self.parent_view.make_embed(), view=self.parent_view)

class HelpView(discord.ui.View):
    def __init__(self, cogs_dict, invoker_id, bot):
        super().__init__(timeout=180)
        self.cogs_dict = cogs_dict  # {cog_name: cog}
        self.invoker_id = invoker_id
        self.bot = bot
        self.current_category = None
        self.current_category_label = None
        self.current_module = None
        self.lines = []
        self.page = 0
        self.per_page = 5

        self.category_counts = {}
        for name, cog in cogs_dict.items():
            key = get_category_for(name)
            self.category_counts[key] = self.category_counts.get(key, 0) + len(cog.get_commands())

        self._rebuild_items()

    def _modules_in_current_category(self):
        return sorted(name for name in self.cogs_dict if get_category_for(name) == self.current_category)

    def _rebuild_items(self):
        self.clear_items()
        self.add_item(MainCategorySelect(self))
        if self.current_category:
            modules = self._modules_in_current_category()
            if modules:
                self.add_item(ModuleSelect(self, modules))
        if self.current_module:
            self.add_item(self.BackButton(self))
            self.add_item(self.NextButton(self))

    class BackButton(discord.ui.Button):
        def __init__(self, parent_view):
            super().__init__(label="◀ Back", style=discord.ButtonStyle.secondary, row=2)
            self.parent_view = parent_view
        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.parent_view.invoker_id:
                return
            self.parent_view.page = max(0, self.parent_view.page - 1)
            await interaction.response.edit_message(embed=self.parent_view.make_embed(), view=self.parent_view)

    class NextButton(discord.ui.Button):
        def __init__(self, parent_view):
            super().__init__(label="Next ▶", style=discord.ButtonStyle.secondary, row=2)
            self.parent_view = parent_view
        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.parent_view.invoker_id:
                return
            self.parent_view.page = min(self.parent_view.max_page, self.parent_view.page + 1)
            await interaction.response.edit_message(embed=self.parent_view.make_embed(), view=self.parent_view)

    def set_category(self, key):
        self.current_category = key
        self.current_category_label = CATEGORIES[key]["label"]
        self.current_module = None
        self.lines = []
        self.page = 0
        self._rebuild_items()

    def set_module(self, module_name):
        self.current_module = module_name
        self.lines = detailed_module_lines(self.cogs_dict[module_name])
        self.page = 0
        self._rebuild_items()

    @property
    def max_page(self):
        return max(0, (len(self.lines) - 1) // self.per_page)

    def make_embed(self):
        if self.current_category is None:
            desc_lines = ["Welcome! Select a category below to inspect tools and modules.\n"]
            for key, info in CATEGORIES.items():
                count = self.category_counts.get(key, 0)
                if count > 0:
                    desc_lines.append(f"{info['label']} — **{count}** command(s)")
            embed = discord.Embed(title="📖 Command Centre", description="\n".join(desc_lines), color=EMBED_COLOR)
            if self.bot.user:
                embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            return embed

        if self.current_module is None:
            modules = self._modules_in_current_category()
            desc = f"Use `~help <command>` for detailed syntax, or select a subcategory below.\n\n"
            for name in modules:
                desc += f"**{name}**\n{compact_module_summary(self.cogs_dict[name])}\n\n"
            embed = discord.Embed(title=self.current_category_label, description=desc.strip(), color=EMBED_COLOR)
            return embed

        start = self.page * self.per_page
        chunk = self.lines[start:start + self.per_page]
        embed = discord.Embed(
            title=f"{self.current_category_label} → {self.current_module}",
            description="Use `~help <command>` for detailed syntax.\n\n" + "\n\n".join(chunk),
            color=EMBED_COLOR,
        )
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This isn't your help menu — run `~help` yourself.", ephemeral=True)
            return False
        return True

class HelpCog(commands.Cog, name="Help"):
    def __init__(self, bot):
        self.bot = bot

    def _visible_cogs(self):
        return {
            name: cog for name, cog in self.bot.cogs.items()
            if name not in EXCLUDED_COGS and cog.get_commands()
        }

    @commands.command(name="help", aliases=["h"])
    async def help_command(self, ctx, *, query: str = None):
        """Shows the Command Centre, or details on one command (~help kick)."""
        cogs_dict = self._visible_cogs()

        if query:
            cmd = self.bot.get_command(query)
            if cmd and not (cmd.cog and cmd.cog.qualified_name in EXCLUDED_COGS) and not cmd.hidden:
                aliases = f" (aliases: {', '.join('~' + a for a in cmd.aliases)})" if cmd.aliases else ""
                help_text = cmd.help or "No description"
                example = None
                if "Example:" in help_text:
                    help_text, _, example = help_text.partition("Example:")
                    help_text = help_text.strip()
                    example = example.strip()
                embed = discord.Embed(
                    title=f"`{usage_line(cmd)}`",
                    description=(help_text + aliases),
                    color=EMBED_COLOR,
                )
                if example:
                    embed.add_field(name="Example", value=f"`{example}`", inline=False)
                if isinstance(cmd, commands.Group):
                    sub_lines = [f"**`{usage_line(c)}`** — {c.help or 'No description'}" for c in cmd.commands]
                    embed.add_field(name="Subcommands", value="\n".join(sub_lines) or "None", inline=False)
                await ctx.send(embed=embed)
                return

            await ctx.send(f"No command called `{query}` found. Try `~help` to browse categories.")
            return

        view = HelpView(cogs_dict, ctx.author.id, self.bot)
        await ctx.send(embed=view.make_embed(), view=view)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
