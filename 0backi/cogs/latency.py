from discord.ext import commands

class Latency(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["lat"])
    async def latency(self, ctx):
        """Shows the bot's current latency to Discord."""
        latency_ms = round(self.bot.latency * 1000)
        await ctx.send(f"Pong! {latency_ms}ms")

async def setup(bot):
    await bot.add_cog(Latency(bot))
