import discord

class ConfirmView(discord.ui.View):
    def __init__(self, author_id, timeout=30):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()

async def ask_confirm(ctx, prompt: str) -> bool:
    view = ConfirmView(ctx.author.id)
    msg = await ctx.send(prompt, view=view)
    await view.wait()
    try:
        await msg.delete()
    except Exception:
        pass
    return bool(view.value)
