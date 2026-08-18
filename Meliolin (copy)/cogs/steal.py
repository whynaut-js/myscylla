import re
import io
import discord
from discord.ext import commands
from utils.permissions import has_botperm
from utils.autodelete import send_temp

EMOJI_RE = re.compile(r"<(a?):(\w+):(\d+)>")

class Steal(commands.Cog):
    """Steal emojis/stickers from other messages or servers, and upload images as new ones."""

    def __init__(self, bot):
        self.bot = bot

    async def _check(self, ctx):
        if not await has_botperm(self.bot, ctx.guild, ctx.author, "manage_roles"):
            await send_temp(ctx, "You don't have permission to manage emojis/stickers.")
            return False
        return True

    @commands.command(name="steal")
    async def steal(self, ctx, *, args: str = None):
        """Steal one or more custom emojis, or upload an attached image as a new emoji.
        Example: ~steal <:cat:1234> cool_cat"""
        if not await self._check(ctx):
            return

        # Attached image → upload as emoji
        if ctx.message.attachments:
            image_bytes = await ctx.message.attachments[0].read()
            name = (args or ctx.message.attachments[0].filename.rsplit(".", 1)[0])[:32]
            name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
            try:
                emoji = await ctx.guild.create_custom_emoji(name=name, image=image_bytes, reason=f"Uploaded by {ctx.author}")
                await send_temp(ctx, f"Added emoji {emoji}!")
            except discord.HTTPException as e:
                await send_temp(ctx, f"Couldn't add emoji: {e}")
            return

        # Gather emoji matches from the command args and/or a replied message
        search_text = args or ""
        if ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                search_text += " " + ref_msg.content
            except discord.NotFound:
                pass

        matches = EMOJI_RE.findall(search_text)
        if not matches:
            await send_temp(ctx, "No emojis found. Paste one/more custom emojis, reply to a message containing them, or attach an image.")
            return

        # If exactly one emoji AND extra text after it, treat extra text as custom name
        custom_name = None
        if len(matches) == 1 and args:
            remaining = EMOJI_RE.sub("", args).strip()
            if remaining:
                custom_name = re.sub(r"[^a-zA-Z0-9_]", "_", remaining)[:32]

        added = []
        failed = []
        for animated, name, emoji_id in matches:
            ext = "gif" if animated else "png"
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
            final_name = custom_name if (custom_name and len(matches) == 1) else name

            try:
                async with self.bot.session.get(url) if hasattr(self.bot, "session") else _fallback_get(url) as resp:
                    image_bytes = await resp.read() if hasattr(resp, "read") else resp
            except Exception:
                failed.append(final_name)
                continue

            try:
                emoji = await ctx.guild.create_custom_emoji(name=final_name, image=image_bytes, reason=f"Stolen by {ctx.author}")
                added.append(str(emoji))
            except discord.HTTPException:
                failed.append(final_name)

        result = []
        if added:
            result.append(f"Added: {' '.join(added)}")
        if failed:
            result.append(f"Failed: `{', '.join(failed)}` (server may be at emoji slot limit)")
        await send_temp(ctx, "\n".join(result) or "Nothing added.")

    @commands.command(name="ssteal")
    async def ssteal(self, ctx, *, name: str = None):
        """Steal sticker(s) — reply to a message containing sticker(s), or attach an image.
        Example: reply to a sticker and run ~ssteal my_sticker_name"""
        if not await self._check(ctx):
            return

        if ctx.message.attachments:
            image_bytes = await ctx.message.attachments[0].read()
            final_name = (name or ctx.message.attachments[0].filename.rsplit(".", 1)[0])[:30]
            try:
                await ctx.guild.create_sticker(
                    name=final_name, description=final_name, emoji="⭐",
                    file=discord.File(io.BytesIO(image_bytes), filename="sticker.png"),
                    reason=f"Uploaded by {ctx.author}"
                )
                await send_temp(ctx, f"Added sticker `{final_name}`!")
            except discord.HTTPException as e:
                await send_temp(ctx, f"Couldn't add sticker: {e}")
            return

        if not ctx.message.reference or not ctx.message.reference.message_id:
            await send_temp(ctx, "Reply to a message containing sticker(s), or attach an image.")
            return

        try:
            ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except discord.NotFound:
            await send_temp(ctx, "Couldn't find that message.")
            return

        if not ref_msg.stickers:
            await send_temp(ctx, "That message has no stickers.")
            return

        added = []
        failed = []
        for i, sticker in enumerate(ref_msg.stickers):
            full_sticker = await sticker.fetch()
            final_name = name if (name and len(ref_msg.stickers) == 1) else sticker.name
            final_name = final_name[:30]
            try:
                image_bytes = await full_sticker.read()
                ext = "png" if full_sticker.format != discord.StickerFormatType.lottie else "json"
                await ctx.guild.create_sticker(
                    name=final_name, description=final_name, emoji="⭐",
                    file=discord.File(io.BytesIO(image_bytes), filename=f"sticker.{ext}"),
                    reason=f"Stolen by {ctx.author}"
                )
                added.append(final_name)
            except discord.HTTPException:
                failed.append(final_name)

        result = []
        if added:
            result.append(f"Added: `{', '.join(added)}`")
        if failed:
            result.append(f"Failed: `{', '.join(failed)}` (server may be at sticker slot limit, or format unsupported)")
        await send_temp(ctx, "\n".join(result) or "Nothing added.")

async def setup(bot):
    await bot.add_cog(Steal(bot))
