"""Auto-chat commands."""

from ..common import *
# ---------------------------------------------------------------------------
# Slash commands â€” Auto-chat mode
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-auto-chat-mode", description="Configure auto-chat mode for a channel")
@app_commands.describe(
    channel="The channel for auto-chat (one at a time)",
    enabled="True = auto-chat active, False = disabled",
    interval="Seconds between checks (default: 30)",
    idle_minutes="Minutes of inactivity before idle mode (default: 10)",
)
@app_commands.default_permissions(administrator=True)
async def set_auto_chat_mode(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    enabled: bool,
    interval: int = 30,
    idle_minutes: int = 10,
):
    if interval < 5:
        await interaction.response.send_message("⚠️ Interval must be at least 5 seconds.", ephemeral=True)
        return
    if idle_minutes < 1:
        await interaction.response.send_message("⚠️ Idle timeout must be at least 1 minute.", ephemeral=True)
        return

    bot_config["auto_chat_channel_id"] = str(channel.id)
    bot_config["auto_chat_enabled"] = enabled
    bot_config["auto_chat_interval"] = interval
    bot_config["auto_chat_idle_minutes"] = idle_minutes
    save_config(bot_config)

    if auto_chat_manager:
        auto_chat_manager.start()

    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Auto-chat **{state}** for {channel.mention}.\n"
        f"• Check interval: **{interval}s**\n"
        f"• Idle timeout: **{idle_minutes}m**",
        ephemeral=True,
    )


@bot.tree.command(name="set-auto-idle-message", description="Set the message posted when auto-chat enters idle mode")
@app_commands.describe(message="The idle message (default: 'Going afk, ping me if you need me')")
@app_commands.default_permissions(administrator=True)
async def set_auto_idle_message(interaction: discord.Interaction, message: str):
    message = message.replace("\\n", "\n")
    bot_config["auto_chat_idle_message"] = message
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Auto-chat idle message set to:\n```{message}```", ephemeral=True
    )



