import asyncio
import discord

async def ask_role(ctx, label):
    """Asks the user to mention an existing role or type 'no'. Returns the role or None."""
    await ctx.send(f"Do you already have a **{label}** role? Mention it (e.g. @{label}), or type `no` to create a new one.")

    def check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    try:
        msg = await ctx.bot.wait_for("message", check=check, timeout=60)
    except asyncio.TimeoutError:
        await ctx.send("Timed out — creating a new one instead.")
        return None

    if msg.content.strip().lower() == "no":
        return None
    if msg.role_mentions:
        return msg.role_mentions[0]

    role = discord.utils.find(lambda r: r.name.lower() == msg.content.strip().lower(), ctx.guild.roles)
    if role is None:
        await ctx.send("Couldn't find that role — creating a new one instead.")
    return role

async def ask_channel(ctx, label):
    """Asks the user to mention an existing channel or type 'no'. Returns the channel or None."""
    await ctx.send(f"Do you already have a **{label}** channel? Mention it (e.g. #{label}), or type `no` to create a new one.")

    def check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    try:
        msg = await ctx.bot.wait_for("message", check=check, timeout=60)
    except asyncio.TimeoutError:
        await ctx.send("Timed out — creating a new one instead.")
        return None

    if msg.content.strip().lower() == "no":
        return None
    if msg.channel_mentions:
        return msg.channel_mentions[0]

    channel = discord.utils.find(lambda c: c.name.lower() == msg.content.strip().lower(), ctx.guild.text_channels)
    if channel is None:
        await ctx.send("Couldn't find that channel — creating a new one instead.")
    return channel
