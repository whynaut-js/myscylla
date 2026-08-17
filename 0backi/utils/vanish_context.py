import discord
from discord.ext import commands
from config.owner import Me
from utils.webhook import get_relay_webhook
from utils.vanish_style import BLANK_NAME, BLANK_AVATAR

ALLOWED_RELAY_KWARGS = {"embed", "embeds", "file", "files", "allowed_mentions", "view"}


class VanishContext(commands.Context):
    """Custom Context: Relays replies through a webhook when vanish mode is active."""

    async def send(self, content=None, **kwargs):
        bot = self.bot
        vanish_blank = getattr(bot, "vanish_blank", False)
        vanish_active = getattr(bot, "vanish_active", False) or vanish_blank
        is_owner_ish = self.author.id in Me or await bot.is_owner(self.author)

        if vanish_active and is_owner_ish and self.guild is not None:
            relay_kwargs = {k: v for k, v in kwargs.items() if k in ALLOWED_RELAY_KWARGS}

            relay_username = BLANK_NAME if vanish_blank else self.author.display_name
            relay_avatar = BLANK_AVATAR if vanish_blank else self.author.display_avatar.url

            try:
                webhook = await get_relay_webhook(bot, self.channel)
                return await webhook.send(
                    content or "",
                    username=relay_username,
                    avatar_url=relay_avatar,
                    wait=True,
                    **relay_kwargs,
                )
            except discord.HTTPException:
                pass  # Fallback to standard reply if webhook fails

        return await super().send(content, **kwargs)
