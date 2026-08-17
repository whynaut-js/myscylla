import sys
import os
import discord
from discord.ext import commands

OWNER_ID = 123456789012345678 

class autosend(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_send_configs = {}
        self.annoy_configs = {}

    # --- PREFIX COMMAND 1: ~autosend ---
    @commands.command(name="autosend")
    async def autosend(self, ctx, *, text: str):
        channel_id = ctx.channel.id

        if text.lower() == "off":
            if channel_id in self.auto_send_configs:
                del self.auto_send_configs[channel_id]
                await ctx.send("❌ Standard auto-send disabled for this channel.")
            else:
                await ctx.send("⚠️ Standard auto-send wasn't active in this channel.")
            return

        self.auto_send_configs[channel_id] = text
        await ctx.send(f'✅ Permanent auto-send activated! Replying with: "{text}"')

    # --- PREFIX COMMAND 2: ~annoy ---
    @commands.command(name="annoy")
    async def annoy(self, ctx, *, text: str):
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

    # --- PREFIX COMMAND 3: ~restart ---
    @commands.command(name="restart")
    @commands.is_owner()
    async def restart(self, ctx):
        await ctx.send("🔄 Restarting bot...")
        channel_id = str(ctx.channel.id)
        os.execv(sys.executable, ['python3', sys.argv[0], channel_id])

    # --- LISTENER ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        channel_id = message.channel.id

        if channel_id in self.auto_send_configs:
            await message.channel.send(self.auto_send_configs[channel_id])

        if channel_id in self.annoy_configs:
            reply_text = self.annoy_configs[channel_id]
            try:
                sent_msg = await message.channel.send(reply_text)
                await sent_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

async def setup(bot):
    await bot.add_cog(autosend(bot))
