import discord

class PaginatorView(discord.ui.View):
    """Generic Next/Back button paginator. Pass it pre-formatted lines,
    it slices them into pages of `per_page` and builds embeds. Mentions
    inside embeds never ping, so this is naturally spam-safe."""

    def __init__(self, lines, title, per_page=9, color=discord.Color.blurple()):
        super().__init__(timeout=120)
        self.lines = lines
        self.title = title
        self.per_page = per_page
        self.page = 0
        self.color = color
        self.max_page = max(0, (len(lines) - 1) // per_page)
        self._update_buttons()

    def _update_buttons(self):
        self.previous_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.max_page

    def make_embed(self):
        start = self.page * self.per_page
        chunk = self.lines[start:start + self.per_page]
        embed = discord.Embed(
            title=self.title,
            description="\n".join(chunk) or "Nothing here.",
            color=self.color,
        )
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1}")
        return embed

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)


class EntryPaginatorView(discord.ui.View):
    """Pages through a list of entries one at a time, using Back/Next
    buttons, calling embed_builder(entry, index, total) for each page."""

    def __init__(self, entries, embed_builder, invoker_id):
        super().__init__(timeout=120)
        self.entries = entries
        self.embed_builder = embed_builder
        self.invoker_id = invoker_id
        self.index = 0
        self._update_buttons()

    def _update_buttons(self):
        self.previous_button.disabled = self.index == 0
        self.next_button.disabled = self.index >= len(self.entries) - 1

    def make_embed(self):
        return self.embed_builder(self.entries[self.index], self.index, len(self.entries))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This isn't your menu — run the command yourself.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)
