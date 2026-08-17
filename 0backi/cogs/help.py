import discord
from discord.ext import commands

EXCLUDED_COGS = {"Owner", "Help"}
EMBED_COLOR = discord.Color.from_rgb(88, 101, 242)

def command_usage(c):
    sig = c.signature
    return f"~{c.qualified_name} {sig}".strip()

def build_lines(cog):
    lines = []
    for cmd in sorted(cog.get_commands(), key=lambda c: c.name):
        if cmd.hidden:
            continue
        aliases = f" ({', '.join('~' + a for a in cmd.aliases)})" if cmd.aliases else ""
        lines.append(f"**`{command_usage(cmd)}`**{aliases}\n{cmd.help or 'No description'}")
        if isinstance(cmd, commands.Group):
            for sub in sorted(cmd.commands, key=lambda c: c.name):
                sub_aliases = f" ({', '.join('~' + a for a in sub.aliases)})" if sub.aliases else ""
                lines.append(f"  ↳ **`{command_usage(sub)}`**{sub_aliases}\n     {sub.help or 'No description'}")
    return lines

class CategorySelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [discord.SelectOption(label=name) for name in parent_view.cogs_dict.keys()]
        super().__init__(placeholder="Browse a category...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.invoker_id:
            await interaction.response.send_message("This isn't your help menu — run `~help` yourself.", ephemeral=True)
            return
        cog_name = self.values[0]
        cog = self.parent_view.cogs_dict[cog_name]
        self.parent_view.current_cog = cog_name
        self.parent_view.lines = build_lines(cog)
        self.parent_view.page = 0
        await interaction.response.edit_message(embed=self.parent_view.make_embed(), view=self.parent_view)

class HelpView(discord.ui.View):
    def __init__(self, cogs_dict, invoker_id, bot, start_category=None):
        super().__init__(timeout=120)
        self.cogs_dict = cogs_dict
        self.invoker_id = invoker_id
        self.bot = bot
        self.current_cog = None
        self.lines = []
        self.page = 0
        self.per_page = 6
        self.add_item(CategorySelect(self))

        if start_category and start_category in cogs_dict:
            self.current_cog = start_category
            self.lines = build_lines(cogs_dict[start_category])

    @property
    def max_page(self):
        return max(0, (len(self.lines) - 1) // self.per_page)

    def make_embed(self):
        if self.current_cog is None:
            embed = discord.Embed(
                title="📖 Command Categories",
                description=(
                    "Pick a category from the dropdown below, or jump straight in with "
                    "`~help <category>` (e.g. `~help roles`).\n\n" +
                    "\n".join(f"• **{name}** — {len(cog.get_commands())} command(s)" for name, cog in self.cogs_dict.items())
                ),
                color=EMBED_COLOR,
            )
            if self.bot.user:
                embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            embed.set_footer(text="Tip: ~help <command> shows full usage for one command")
            return embed

        start = self.page * self.per_page
        chunk = self.lines[start:start + self.per_page]
        embed = discord.Embed(
            title=f"📂 {self.current_cog}",
            description="\n\n".join(chunk) or "No commands.",
            color=EMBED_COLOR,
        )
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1} • ~help <command> for full details")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This isn't your help menu — run `~help` yourself.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.max_page, self.page + 1)
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

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
        """Shows this menu, jumps to a category (~help roles), or details on one command (~help kick)."""
        cogs_dict = self._visible_cogs()

        if query:
            cmd = self.bot.get_command(query)
            if cmd and not (cmd.cog and cmd.cog.qualified_name in EXCLUDED_COGS) and not cmd.hidden:
                aliases = f" (aliases: {', '.join('~' + a for a in cmd.aliases)})" if cmd.aliases else ""
                embed = discord.Embed(
                    title=f"`{command_usage(cmd)}`",
                    description=(cmd.help or "No description") + aliases,
                    color=EMBED_COLOR,
                )
                if isinstance(cmd, commands.Group):
                    sub_lines = [f"**`{command_usage(c)}`** — {c.help or 'No description'}" for c in cmd.commands]
                    embed.add_field(name="Subcommands", value="\n".join(sub_lines) or "None", inline=False)
                await ctx.send(embed=embed)
                return

            matched_cat = next((name for name in cogs_dict if name.lower() == query.lower()), None)
            if matched_cat:
                view = HelpView(cogs_dict, ctx.author.id, self.bot, start_category=matched_cat)
                await ctx.send(embed=view.make_embed(), view=view)
                return

            await ctx.send(f"No command or category called `{query}` found. Try `~help` to browse.")
            return

        view = HelpView(cogs_dict, ctx.author.id, self.bot)
        await ctx.send(embed=view.make_embed(), view=view)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
