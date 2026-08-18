import discord

async def get_relay_webhook(bot, channel: discord.TextChannel) -> discord.Webhook:
    """Shared webhook used to send messages styled as a specific member
    (pingrole's relayed pings, mimic's impersonation). Reuses the same
    webhook per channel instead of creating a new one every call."""
    webhooks = await channel.webhooks()
    for wh in webhooks:
        if wh.name == "PingRelay" and wh.user == bot.user:
            return wh
    return await channel.create_webhook(name="PingRelay", reason="For message relaying (pingrole/mimic)")
