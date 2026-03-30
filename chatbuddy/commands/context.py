"""Channel, context, dynamic prompt, and word game commands."""

from ..common import *
# ---------------------------------------------------------------------------
# Slash commands â€” Channel / context settings
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-allowed-channel", description="Whitelist or blacklist a channel for the bot")
@app_commands.describe(
    channel="The channel to configure",
    enabled="True = bot responds in this channel, False = bot ignores this channel",
)
@app_commands.default_permissions(administrator=True)
async def set_allowed_channel(interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool):
    allowed = bot_config.get("allowed_channels", {})
    allowed[str(channel.id)] = enabled
    bot_config["allowed_channels"] = allowed
    save_config(bot_config)
    state = "whitelisted" if enabled else "blacklisted"
    await interaction.response.send_message(f"✅ {channel.mention} has been **{state}**.", ephemeral=True)


@bot.tree.command(name="set-ce", description="Enable/disable [ce] context cutoff for a channel")
@app_commands.describe(
    channel="The channel to configure",
    enabled="True = [ce] cuts off context (default), False = [ce] is ignored",
)
@app_commands.default_permissions(administrator=True)
async def set_ce(interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool):
    ce_channels = bot_config.get("ce_channels", {})
    ce_channels[str(channel.id)] = enabled
    bot_config["ce_channels"] = ce_channels
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ `[ce]` context cutoff **{state}** for {channel.mention}.", ephemeral=True
    )


# ---------------------------------------------------------------------------
# Slash commands â€” Stream of Consciousness (SoC)
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-soc", description="Configure the Stream of Consciousness thoughts channel")
@app_commands.describe(
    channel="The channel where the bot's thoughts will be posted",
    enabled="True = extract thoughts to channel, False = disabled",
)
@app_commands.default_permissions(administrator=True)
async def set_soc(interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool):
    bot_config["soc_channel_id"] = str(channel.id)
    if enabled:
        bot_config["soc_enabled"] = True
        save_config(bot_config)
        await interaction.response.send_message(
            f"✅ SoC thoughts channel set to {channel.mention} — **enabled**.\n"
            f"Text between `<my-thoughts>` and `</my-thoughts>` will be extracted and posted there.",
            ephemeral=True,
        )
    else:
        bot_config["soc_enabled"] = False
        save_config(bot_config)
        await interaction.response.send_message(
            f"✅ SoC thoughts channel set to {channel.mention} — **disabled**.",
            ephemeral=True,
        )


@bot.tree.command(name="set-soc-context", description="Enable cross-channel thought context from the SoC channel")
@app_commands.describe(
    enabled="True = read past thoughts as context, False = disabled",
    count="Number of recent thought messages to read (default: 10)",
)
@app_commands.default_permissions(administrator=True)
async def set_soc_context(interaction: discord.Interaction, enabled: bool, count: int = 10):
    if enabled and not bot_config.get("soc_channel_id"):
        await interaction.response.send_message(
            "⚠️ No SoC channel configured yet. Run `/set-soc` first to set a thoughts channel.",
            ephemeral=True,
        )
        return
    if count < 1:
        await interaction.response.send_message("⚠️ Count must be at least 1.", ephemeral=True)
        return
    bot_config["soc_context_enabled"] = enabled
    bot_config["soc_context_count"] = count
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ SoC context **{state}** — reading last **{count}** thought messages.",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Slash commands â€” Dynamic system prompt
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-dynamic-system-prompt", description="Set an extra dynamic system prompt (appended after main)")
@app_commands.describe(
    prompt="The dynamic prompt text",
    enabled="True = active, False = disabled",
)
@app_commands.default_permissions(administrator=True)
async def set_dynamic_system_prompt(interaction: discord.Interaction, prompt: str, enabled: bool):
    prompt = prompt.replace("\\n", "\n")
    bot_config["dynamic_prompt"] = prompt
    bot_config["dynamic_prompt_enabled"] = enabled
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Dynamic system prompt **{state}** and saved.", ephemeral=True
    )


# ---------------------------------------------------------------------------
# Slash commands â€” Word game
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-word-game", description="Set the word game rules prompt + enable/disable")
@app_commands.describe(
    prompt="Game rules prompt (use {secret-word} as placeholder)",
    enabled="True = word game active, False = disabled",
)
@app_commands.default_permissions(administrator=True)
async def set_word_game(interaction: discord.Interaction, prompt: str, enabled: bool):
    prompt = prompt.replace("\\n", "\n")
    bot_config["word_game_prompt"] = prompt
    bot_config["word_game_enabled"] = enabled
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Word game **{state}**.\n"
        f"Prompt contains `{{secret-word}}`: **{'yes' if '{secret-word}' in prompt else 'no'}**",
        ephemeral=True,
    )


@bot.tree.command(name="set-word-game-selector-prompt", description="Set the hidden-turn prompt for selecting a secret word")
@app_commands.describe(prompt="Instruction appended to main prompt for the hidden word-selection turn")
@app_commands.default_permissions(administrator=True)
async def set_word_game_selector_prompt(interaction: discord.Interaction, prompt: str):
    prompt = prompt.replace("\\n", "\n")
    bot_config["word_game_selector_prompt"] = prompt
    save_config(bot_config)
    await interaction.response.send_message(
        "✅ Word game selector prompt saved.", ephemeral=True
    )


@bot.tree.command(name="set-secret-word", description="Trigger a hidden turn to pick a new secret word")
@app_commands.describe(prompt="Theme or constraint for the secret word (e.g. 'animals', 'foods')")
async def set_secret_word(interaction: discord.Interaction, prompt: str):
    # --- Role-based permission check ---
    allowed_roles = [str(r) for r in bot_config.get("secret_word_allowed_roles", [])]
    is_admin = False
    has_role = False
    
    if getattr(interaction, "guild", None) and isinstance(interaction.user, discord.Member):
        is_admin = interaction.user.guild_permissions.administrator
        has_role = any(str(role.id) in allowed_roles for role in interaction.user.roles)
        
    if not is_admin and not has_role:
        await interaction.response.send_message(
            "⚠️ You don't have permission to use this command. "
            "Ask an admin to grant your role access via `/set-secret-word-permission`.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    # Build hidden-turn system prompt: main + selector only
    main_prompt = bot_config.get("system_prompt", "")
    selector = bot_config.get("word_game_selector_prompt", "")
    hidden_sys = (main_prompt + "\n\n" + selector).strip() if selector else main_prompt

    hidden_response, _, _, _ = await generate(
        prompt=prompt,
        context="",
        config=bot_config,
        system_prompt_override=hidden_sys,
    )

    # Parse {secret-word:WORD} from the response
    word_match = re.search(r"\{secret-word:(.+?)\}", hidden_response)
    if word_match:
        secret = word_match.group(1).strip()
        bot_config["secret_word"] = secret
        save_config(bot_config)
        await interaction.followup.send("✅ A new secret word has been set!", ephemeral=True)
    else:
        await interaction.followup.send(
            "⚠️ Could not parse a secret word from the hidden turn. "
            "Make sure the selector prompt instructs the model to output `{secret-word:WORD}`.",
            ephemeral=True,
        )


@bot.tree.command(name="set-secret-word-permission", description="Grant or revoke a role's access to /set-secret-word")
@app_commands.describe(
    role="The role to configure",
    allowed="True = grant access, False = revoke access",
)
@app_commands.default_permissions(administrator=True)
async def set_secret_word_permission(interaction: discord.Interaction, role: discord.Role, allowed: bool):
    roles_list: list = bot_config.get("secret_word_allowed_roles", [])
    role_id = str(role.id)
    if allowed:
        if role_id not in roles_list:
            roles_list.append(role_id)
        action = "granted"
    else:
        if role_id in roles_list:
            roles_list.remove(role_id)
        action = "revoked"
    bot_config["secret_word_allowed_roles"] = roles_list
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ `/set-secret-word` access **{action}** for role **{role.name}**.",
        ephemeral=True,
    )



