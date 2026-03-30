"""Bot response and heartbeat control commands."""

from ..common import *
# ---------------------------------------------------------------------------
# Slash commands â€” Bot-to-bot response control
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-respond-to-bot", description="Enable or disable responding to other bots")
@app_commands.describe(enabled="True to respond to bots, False to ignore them")
@app_commands.default_permissions(administrator=True)
async def set_respond_to_bot(interaction: discord.Interaction, enabled: bool):
    bot_config["respond_to_bot"] = enabled
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Responding to other bots is now **{state}**.",
        ephemeral=True,
    )


@bot.tree.command(name="set-respond-bot-limit", description="Set how many consecutive bot messages before stopping replies (1-9)")
@app_commands.describe(limit="Threshold: stop if the last N messages are all from bots/apps (1-9)")
@app_commands.default_permissions(administrator=True)
async def set_respond_bot_limit(interaction: discord.Interaction, limit: int):
    if limit < 1 or limit > 9:
        await interaction.response.send_message(
            "❌ Limit must be between 1 and 9.", ephemeral=True
        )
        return
    bot_config["respond_bot_limit"] = limit
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Bot-to-bot reply limit set to **{limit}** consecutive bot messages.",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Slash commands â€” Heartbeat
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-heartbeat", description="Configure periodic heartbeat messages")
@app_commands.describe(
    enabled="True to enable, False to disable",
    interval="Interval in minutes between heartbeats",
    channel="Channel to post heartbeat messages in",
    prompt="The input prompt the bot receives each heartbeat",
)
@app_commands.default_permissions(administrator=True)
async def set_heartbeat_cmd(
    interaction: discord.Interaction,
    enabled: bool,
    interval: int,
    channel: discord.TextChannel,
    prompt: str,
):
    bot_config["heartbeat_enabled"] = enabled
    bot_config["heartbeat_interval_minutes"] = max(1, interval)
    bot_config["heartbeat_channel_id"] = str(channel.id)
    bot_config["heartbeat_prompt"] = prompt
    save_config(bot_config)

    # Restart the heartbeat manager with new settings
    if heartbeat_manager:
        heartbeat_manager.stop()
    heartbeat_manager.set(HeartbeatManager(bot, bot_config))
    heartbeat_manager.start()

    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Heartbeat **{state}** — every **{max(1, interval)}min** in {channel.mention}.",
        ephemeral=True,
    )




