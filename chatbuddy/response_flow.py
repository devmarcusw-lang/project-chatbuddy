"""Message generation and response flow."""

from .common import *
# Core response helpers (extracted from on_message)
# ---------------------------------------------------------------------------

async def _generate_and_respond(message: discord.Message):
    """Handle a single mention/reply â€” the normal response flow."""
    if _tama_hatching_active():
        await message.reply(
            build_hatching_message(bot_config),
            mention_author=False,
        )
        return
    if bot_config.get("tama_enabled", False) and tama_manager:
        tama_manager.record_interaction()
    if bot_config.get("tama_enabled", False) and is_sleeping(bot_config):
        return

    async with message.channel.typing():
        user_text = strip_mention(message.content, bot.user.id)
        if not user_text:
            user_text = "(empty message)"
        user_text = await _inject_duck_search_context(user_text)

        history_limit = bot_config.get("chat_history_limit", 40)
        history_messages = await collect_context_entries(
            message.channel,
            history_limit,
            config=bot_config,
            before=message,
        )

        ce_channels = bot_config.get("ce_channels", {})
        channel_key = str(message.channel.id)
        ce_enabled = ce_channels.get(channel_key, True)
        context = format_context(history_messages, ce_enabled=ce_enabled)

        # SoC context injection (after chat history)
        context += await _read_soc_context(bot, bot_config)

        attachments_data = []
        if bot_config.get("multimodal_enabled", False):
            for a in message.attachments:
                if a.content_type and (a.content_type.startswith("image/") or a.content_type.startswith("audio/")):
                    file_bytes = await a.read()
                    attachments_data.append({"mime_type": a.content_type, "data": file_bytes})

        response_text, audio_bytes, soul_logs, reminder_cmds = await generate(
            user_text, context, bot_config,
            speaker_name=message.author.display_name,
            speaker_id=str(message.author.id),
            attachments=attachments_data,
        )

        # Tamagotchi: deplete stats after generate
        death_msg = deplete_stats(bot_config)
        is_dead = False
        started_sleep = _maybe_begin_auto_rest(message.channel.id)
        if death_msg:
            response_text = (response_text + "\n\n" + death_msg) if response_text else death_msg
            is_dead = True

        # AI-triggered 2-stage turn for Web Search
        if bot_config.get("duck_search_enabled", False):
            response_text, audio_bytes, soul_logs2, reminder_cmds2, ran_duck_second_turn = await _resolve_model_duck_search(
                response_text,
                context,
                bot_config,
                speaker_name=message.author.display_name,
                speaker_id=str(message.author.id),
            )
            if ran_duck_second_turn:
                # Tamagotchi: deplete stats for the second inference too
                death_msg2 = deplete_stats(bot_config)
                started_sleep = _maybe_begin_auto_rest(message.channel.id) or started_sleep
                if death_msg2:
                    response_text = (response_text + "\n\n" + death_msg2) if response_text else death_msg2
                    is_dead = True
                if soul_logs2: soul_logs.extend(soul_logs2)
                if reminder_cmds2: reminder_cmds.extend(reminder_cmds2)

        # Apply any reminder/wake-time commands the bot emitted
        if reminder_cmds and reminder_manager:
            await reminder_manager._apply_commands(reminder_cmds, source_channel_id=str(message.channel.id))

        # SoC thought extraction
        response_text = await _handle_soc_extraction(response_text, bot, bot_config)

        # Resolve custom emoji shortcodes before sending
        response_text = resolve_custom_emoji(response_text, message.guild)

        # Tamagotchi: build button view if enabled
        tama_view = _build_tama_view()
        if tama_view:
            response_text = append_tamagotchi_footer(response_text, bot_config, tama_manager)

        if audio_bytes:
            audio_file = discord.File(fp=io.BytesIO(audio_bytes), filename="chatbuddy_voice.wav")
            await message.reply(file=audio_file, mention_author=False)
            chunks = chunk_message(response_text)
            for i, chunk in enumerate(chunks):
                # Attach tama view to the last text chunk
                v = tama_view if (i == len(chunks) - 1 and tama_view) else None
                await message.channel.send(chunk, view=v)
        else:
            chunks = chunk_message(response_text)
            for i, chunk in enumerate(chunks):
                # Attach tama view to the last chunk
                v = tama_view if (i == len(chunks) - 1 and tama_view) else None
                if i == 0:
                    await message.reply(chunk, mention_author=False, view=v)
                else:
                    await message.channel.send(chunk, view=v)
        if started_sleep and tama_manager:
            await tama_manager.send_sleep_announcement(message.channel.id)

        # Send soul logs to configured channel if present
        if soul_logs and bot_config.get("soul_channel_enabled"):
            ch_id = bot_config.get("soul_channel_id")
            if ch_id:
                soul_ch = bot.get_channel(int(ch_id))
                if soul_ch:
                    joined_logs = "\n".join(soul_logs)
                    for log_chunk in chunk_message(joined_logs, limit=1900):
                        await soul_ch.send(f"**🧠 Soul Updates:**\n{log_chunk}")

        if is_dead:
            await broadcast_death(bot, bot_config)


async def _generate_batched_response(channel: discord.TextChannel, batch: list[discord.Message]):
    """
    Process a batch of messages that arrived during generation.
    Formats them as a single chatlog input and generates one response.
    """
    if _tama_hatching_active():
        await channel.send(build_hatching_message(bot_config))
        return
    if bot_config.get("tama_enabled", False) and tama_manager:
        tama_manager.record_interaction()
    if bot_config.get("tama_enabled", False) and is_sleeping(bot_config):
        return

    async with channel.typing():
        # Build the batched input showing who said what
        batch_lines = []
        for msg in batch:
            user_text = strip_mention(msg.content, bot.user.id)
            if not user_text:
                user_text = "(empty message)"
            batch_lines.append(f"[{msg.author.display_name}]: {user_text}")
        batched_input = (
            "[MULTIPLE MESSAGES RECEIVED — respond to all of them naturally]\n"
            + "\n".join(batch_lines)
        )
        batched_input = await _inject_duck_search_context(batched_input)

        history_limit = bot_config.get("chat_history_limit", 40)
        history_messages = await collect_context_entries(
            channel,
            history_limit,
            config=bot_config,
        )

        ce_channels = bot_config.get("ce_channels", {})
        channel_key = str(channel.id)
        ce_enabled = ce_channels.get(channel_key, True)
        context = format_context(history_messages, ce_enabled=ce_enabled)

        context += await _read_soc_context(bot, bot_config)

        attachments_data = []
        if bot_config.get("multimodal_enabled", False):
            for m in batch:
                for a in m.attachments:
                    if a.content_type and (a.content_type.startswith("image/") or a.content_type.startswith("audio/")):
                        file_bytes = await a.read()
                        attachments_data.append({"mime_type": a.content_type, "data": file_bytes})

        # Use the last message's author info for speaker metadata
        last_msg = batch[-1]
        response_text, audio_bytes, soul_logs, reminder_cmds = await generate(
            batched_input, context, bot_config,
            speaker_name=last_msg.author.display_name,
            speaker_id=str(last_msg.author.id),
            attachments=attachments_data,
        )

        # Tamagotchi: deplete stats after generate
        death_msg = deplete_stats(bot_config)
        is_dead = False
        started_sleep = _maybe_begin_auto_rest(channel.id)
        if death_msg:
            response_text = (response_text + "\n\n" + death_msg) if response_text else death_msg
            is_dead = True

        # AI-triggered 2-stage turn for Web Search
        if bot_config.get("duck_search_enabled", False):
            response_text, audio_bytes, soul_logs2, reminder_cmds2, ran_duck_second_turn = await _resolve_model_duck_search(
                response_text,
                context,
                bot_config,
                speaker_name=last_msg.author.display_name,
                speaker_id=str(last_msg.author.id),
            )
            if ran_duck_second_turn:
                # Tamagotchi: deplete stats for the second inference too
                death_msg2 = deplete_stats(bot_config)
                started_sleep = _maybe_begin_auto_rest(channel.id) or started_sleep
                if death_msg2:
                    response_text = (response_text + "\n\n" + death_msg2) if response_text else death_msg2
                    is_dead = True
                if soul_logs2: soul_logs.extend(soul_logs2)
                if reminder_cmds2: reminder_cmds.extend(reminder_cmds2)

        if reminder_cmds and reminder_manager:
            await reminder_manager._apply_commands(reminder_cmds, source_channel_id=str(channel.id))

        response_text = await _handle_soc_extraction(response_text, bot, bot_config)
        response_text = resolve_custom_emoji(response_text, channel.guild)

        # Tamagotchi: build button view if enabled
        tama_view = _build_tama_view()
        if tama_view:
            response_text = append_tamagotchi_footer(response_text, bot_config, tama_manager)

        if audio_bytes:
            audio_file = discord.File(fp=io.BytesIO(audio_bytes), filename="chatbuddy_voice.wav")
            await channel.send(file=audio_file)
            chunks = chunk_message(response_text)
            for i, chunk in enumerate(chunks):
                v = tama_view if (i == len(chunks) - 1 and tama_view) else None
                await channel.send(chunk, view=v)
        else:
            chunks = chunk_message(response_text)
            for i, chunk in enumerate(chunks):
                v = tama_view if (i == len(chunks) - 1 and tama_view) else None
                await channel.send(chunk, view=v)
        if started_sleep and tama_manager:
            await tama_manager.send_sleep_announcement(channel.id)

        if soul_logs and bot_config.get("soul_channel_enabled"):
            ch_id = bot_config.get("soul_channel_id")
            if ch_id:
                soul_ch = bot.get_channel(int(ch_id))
                if soul_ch:
                    joined_logs = "\n".join(soul_logs)
                    for log_chunk in chunk_message(joined_logs, limit=1900):
                        await soul_ch.send(f"**🧠 Soul Updates:**\n{log_chunk}")

        if is_dead:
            await broadcast_death(bot, bot_config)



