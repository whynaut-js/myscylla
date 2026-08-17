import discord

DEFAULT_DELAY = 8

async def send_temp(ctx_or_channel, content=None, *, delay=DEFAULT_DELAY, **kwargs):
    """Sends a message and auto-deletes it after `delay` seconds. Use for
    transient confirmations/errors (e.g. "Kicked user", "Bad argument
    provided.") — NOT for anything meant to stay readable (~help, ~lr,
    ~modcase, giveaway announcements, etc — those just use ctx.send directly)."""
    msg = await ctx_or_channel.send(content, **kwargs)
    try:
        await msg.delete(delay=delay)
    except discord.HTTPException:
        pass
    return msg
