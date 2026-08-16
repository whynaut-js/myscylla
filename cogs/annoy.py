import discord
from discord.ext import commands

class Annoy(commands.Cog):
    """Ghost reply cog that sends and immediately deletes messages in designated channels."""

    def __init__(self, bot):
        self.bot = bot
        self.annoy_configs = {}  # { channel_id: "message" }

    @commands.command(name="annoy")
    async def annoy(self, ctx, *, text: str):
        """Set an instant flash auto-reply that vanishes immediately."""
        channel_id = ctx.channel.id

        if text.lower() == "off":
            if channel_id in self.annoy_configs:
                del self.annoy_configs[channel_id]
                await ctx.send("❌ Ghost auto-reply disabled for this channel.")
            else:
                await ctx.send("⚠️ Ghost auto-reply wasn't active in this channel.")
            return

        self.annoy_configs[channel_id] = text
        await ctx.send(f'👻 Annoy mode activated! Flashing ghost message: "{text}"')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        channel_id = message.channel.id

        if channel_id in self.annoy_configs:
            reply_text = self.annoy_configs[channel_id]
            try:
                sent_msg = await message.channel.send(reply_text)
                await sent_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

async def setup(bot):
    await bot.add_cog(Annoy(bot))
