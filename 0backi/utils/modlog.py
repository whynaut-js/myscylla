import discord

async def log_case(bot, guild, action, moderator, target, reason):
    """Records a moderation action and posts it to the modlog channel, if set. Returns the new case number."""
    row = await bot.db.fetchone(
        "SELECT MAX(case_id) FROM mod_cases WHERE guild_id = ?", (guild.id,)
    )
    next_id = (row[0] or 0) + 1
    timestamp = discord.utils.utcnow().isoformat()

    await bot.db.execute(
        """
        INSERT INTO mod_cases (guild_id, case_id, action, moderator_id, target_id, reason, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (guild.id, next_id, action, moderator.id, target.id, reason, timestamp),
    )

    config_row = await bot.db.fetchone(
        "SELECT modlog_channel_id FROM guild_config WHERE guild_id = ?", (guild.id,)
    )
    if config_row and config_row[0]:
        channel = guild.get_channel(config_row[0])
        if channel:
            embed = discord.Embed(
                title=f"Case #{next_id} — {action.capitalize()}",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Target", value=f"{target.mention} ({target.id})", inline=False)
            embed.add_field(name="Moderator", value=f"{moderator.mention} ({moderator.id})", inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    return next_id
