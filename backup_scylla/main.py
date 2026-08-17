import os
import random
import aiosqlite
import logging
from logging.handlers import TimedRotatingFileHandler
import discord
from discord.ext import commands
from config.settings import TOKEN, PREFIX
from config.owner import Me
from utils.database import Database
from utils.vanish_context import VanishContext
from utils.vanish_style import BLANK_NAME, BLANK_AVATAR
from utils.webhook import get_relay_webhook
from utils.autodelete import send_temp

file_handler = TimedRotatingFileHandler(
    "bot.log",
    when="midnight",
    backupCount=21,
    encoding="utf-8"
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[
        file_handler,
        logging.StreamHandler()
    ]
)
log = logging.getLogger("main")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.invites = True


async def get_prefix(bot, message):
    if message.guild:
        row = await bot.db.fetchone(
            "SELECT prefix FROM guild_config WHERE guild_id = ?", (message.guild.id,)
        )
        guild_prefix = row[0] if row and row[0] else PREFIX
    else:
        guild_prefix = PREFIX

    is_priv = message.author.id in Me or await bot.is_owner(message.author)

    prefixes = [guild_prefix]
    if is_priv:
        if "~" not in prefixes:
            prefixes.append("~")
        prefixes.append("")
    else:
        grant_row = await bot.db.fetchone(
            "SELECT 1 FROM noprefix_grants WHERE user_id = ?", (message.author.id,)
        )
        if grant_row is not None:
            prefixes.append("")

    return commands.when_mentioned_or(*prefixes)(bot, message)


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            help_command=None,
        )
        self.vanish_active = False
        self.vanish_blank = False

    async def get_context(self, message, *, cls=VanishContext):
        return await super().get_context(message, cls=cls)

    async def setup_hook(self):
        app_info = await self.application_info()
        self.owner_id = app_info.owner.id
        self.db = Database("bot.db")
        await self.db.setup()

        try:
            row = await self.db.fetchone("SELECT value FROM bot_settings WHERE key = 'vanish_active'")
            self.vanish_active = (row is not None and row[0] == "1")
        except Exception:
            self.vanish_active = False

        try:
            row = await self.db.fetchone("SELECT value FROM bot_settings WHERE key = 'vanish_blank'")
            self.vanish_blank = (row is not None and row[0] == "1")
        except Exception:
            self.vanish_blank = False

        for filename in sorted(os.listdir("./cogs")):
            if filename.endswith(".py") and not filename.startswith("_"):
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    log.info(f"Loaded cogs.{filename[:-3]}")
                except Exception:
                    log.exception(f"Failed to load cogs.{filename[:-3]} — skipping, other cogs will still load")

bot = MyBot()

global_cooldown = commands.CooldownMapping.from_cooldown(1, 2.52, commands.BucketType.user)

@bot.before_invoke
async def apply_global_cooldown(ctx):
    if ctx.command and ctx.command.cog and ctx.command.cog.qualified_name == "Owner":
        return
    if ctx.author.id in Me or await ctx.bot.is_owner(ctx.author):
        return
    bucket = global_cooldown.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()
    if retry_after:
        raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.user)

@bot.event
async def on_ready():
    log.info(f"running as {bot.user}")
    log.info(f"owner_id: {bot.owner_id}, owner_ids: {bot.owner_ids}")
    if os.path.exists("restart_info.txt"):
        with open("restart_info.txt", "r") as f:
            lines = f.read().splitlines()

        try:
            channel_id = int(lines[0])
            message_id = int(lines[1])
            is_vanish = lines[2] == "1" if len(lines) >= 3 else False
        except (IndexError, ValueError):
            os.remove("restart_info.txt")
            return

        os.remove("restart_info.txt")

        channel = bot.get_channel(channel_id)
        if channel:
            if is_vanish:
                log.info(f"on_ready vanish branch: channel_id={channel_id}, vanish_blank={getattr(bot, 'vanish_blank', False)}")
                try:
                    vanish_blank = getattr(bot, "vanish_blank", False)
                    webhook = await get_relay_webhook(bot, channel)
                    relay_username = BLANK_NAME if vanish_blank else "Owner"
                    relay_avatar = BLANK_AVATAR if vanish_blank else bot.user.display_avatar.url
                    await webhook.send(
                        random.choice(["back~", "😊", "reconnected", "ok i'm good now"]),
                        username=relay_username,
                        avatar_url=relay_avatar,
                    )
                    log.info("on_ready vanish webhook send succeeded")
                except Exception:
                    log.exception("on_ready vanish webhook send FAILED")
            else:
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(content="I'm online!")
                except (discord.NotFound, discord.Forbidden):
                    await channel.send("I'm online!")

# --- ADDED: EDITED MESSAGE COMMAND HANDLING ---
@bot.event
async def on_message_edit(before, after):
    if after.author.bot or before.content == after.content:
        return
    await bot.process_commands(after)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await send_temp(ctx, f"Missing argument: `{error.param.name}`")
        return
    if isinstance(error, commands.BadArgument):
        await send_temp(ctx, "Bad argument provided.")
        return
    if isinstance(error, commands.CommandOnCooldown):
        await send_temp(ctx, f"Slow down — try again in {error.retry_after:.1f}s.")
        return
    if isinstance(error, commands.CommandInvokeError) and isinstance(error.original, aiosqlite.Error):
        log.error(f"Database error in command '{ctx.command}': {error.original}", exc_info=error.original)
        await send_temp(ctx, "Database error — this has been logged.")
        return

    log.error(f"Unhandled error in command '{ctx.command}': {error}", exc_info=error)
    await send_temp(ctx, "Something went wrong running that command.")

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception:
        log.exception("Bot crashed before/during startup")
