"""Runtime management and public helpers for the Tamagotchi feature."""

from .common import *
from .state import *


def _build_tama_view(config: dict, manager):
    from .views import TamagotchiView

    return TamagotchiView(config, manager)


async def _send_soul_logs(bot_ref, config: dict, soul_logs: list[str]) -> None:
    from bot_helpers import send_soul_logs

    await send_soul_logs(bot_ref, config, soul_logs)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TamagotchiManager  â€” runtime state that doesn't belong in config.json
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TamagotchiManager:
    """
    Manages ephemeral runtime state:
      â€¢ Global button cooldowns  (dict[str, float] â€” action â†’ timestamp)
      â€¢ Loneliness timer          (asyncio.Task or None)
      â€¢ Energy recharge timer     (asyncio.Task or None)
      â€¢ Poop grace timer          (asyncio.Task or None)
      â€¢ RPS pending games         (dict[int, str] â€” message_id â†’ bot_choice)
    """

    def __init__(self, bot: discord.Client, config: dict):
        self.bot = bot
        self.config = config
        self._cooldowns: dict[str, float] = {}     # action -> expiry epoch
        self._dirt_task: asyncio.Task | None = None
        self._energy_task: asyncio.Task | None = None
        self._energy_expiry: float = 0.0
        self._lonely_task: asyncio.Task | None = None
        self._sleep_task: asyncio.Task | None = None
        self._sleep_expiry: float = 0.0
        self._hatch_task: asyncio.Task | None = None
        self._hatch_expiry: float = 0.0
        self._poop_tasks: set[asyncio.Task] = set()
        self._rps_games: dict[int, str] = {}        # msg_id -> bot_choice

    # â”€â”€ lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def start(self):
        """Start background tasks if tama is enabled."""
        if self.config.get("tama_enabled", False):
            self._resume_sleep_state()
            self._resume_hatching_state()
            self._sync_dirt_grace()
            apply_loneliness(self.config, save=True)
            now = time.time()
            if float(self.config.get("tama_last_interaction_at", 0.0) or 0.0) <= 0.0:
                self.config["tama_last_interaction_at"] = now
                self.config["tama_lonely_last_update_at"] = now
                save_config(self.config)
            self._start_energy_task()
            self._start_lonely_task()

    def stop(self):
        if self._dirt_task and not self._dirt_task.done():
            self._dirt_task.cancel()
        if self._energy_task and not self._energy_task.done():
            self._energy_task.cancel()
        if self._lonely_task and not self._lonely_task.done():
            self._lonely_task.cancel()
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        if self._hatch_task and not self._hatch_task.done():
            self._hatch_task.cancel()
        for task in list(self._poop_tasks):
            task.cancel()
        self._poop_tasks.clear()

    # â”€â”€ cooldowns â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def check_cooldown(self, action: str) -> float:
        """
        Return 0.0 if *action* is off cooldown.
        Otherwise return seconds remaining.
        """
        expiry = self._cooldowns.get(action, 0.0)
        remaining = expiry - time.time()
        return max(0.0, remaining)

    def set_cooldown(self, action: str, seconds: int):
        self._cooldowns[action] = time.time() + seconds

    # â€”â€” interaction / energy recharge â€”â€”â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“

    def record_interaction(self, *, save: bool = True):
        if not self.config.get("tama_enabled", False):
            return
        now = time.time()
        self.config["tama_last_interaction_at"] = now
        self.config["tama_lonely_last_update_at"] = now
        if save:
            save_config(self.config)
        self._start_energy_task()
        self._start_lonely_task()

    def _start_energy_task(self):
        interval = max(1, int(self.config.get("tama_energy_recharge_interval", 300)))
        self._energy_expiry = time.time() + interval
        if self._energy_task and not self._energy_task.done():
            self._energy_task.cancel()
        self._energy_task = asyncio.create_task(self._energy_recharge_loop())

    async def _energy_recharge_loop(self):
        try:
            while True:
                interval = max(1, int(self.config.get("tama_energy_recharge_interval", 300)))
                self._energy_expiry = time.time() + interval
                await asyncio.sleep(interval)
                current = float(self.config.get("tama_energy", 0))
                maximum = float(self.config.get("tama_energy_max", 100))
                recharge = max(0.0, float(self.config.get("tama_energy_recharge_amount", 5.0)))
                self.config["tama_energy"] = min(maximum, round(current + recharge, 2))
                save_config(self.config)
        except asyncio.CancelledError:
            return

    def _start_lonely_task(self):
        if self._lonely_task and not self._lonely_task.done():
            self._lonely_task.cancel()
        self._lonely_task = asyncio.create_task(self._lonely_loop())

    async def _lonely_loop(self):
        try:
            while True:
                last_update = max(
                    float(self.config.get("tama_last_interaction_at", 0.0) or 0.0),
                    float(self.config.get("tama_lonely_last_update_at", 0.0) or 0.0),
                )
                if last_update <= 0.0:
                    last_update = time.time()
                    self.config["tama_last_interaction_at"] = last_update
                    self.config["tama_lonely_last_update_at"] = last_update
                    save_config(self.config)
                next_due_at = loneliness_next_due_at(self.config)
                if next_due_at == float("inf"):
                    await asyncio.sleep(60)
                    continue
                sleep_for = max(1.0, next_due_at - time.time())
                await asyncio.sleep(sleep_for)
                apply_loneliness(self.config, save=True)
        except asyncio.CancelledError:
            return

    # â€”â€” sleep / rest â€”â€”â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“

    @property
    def sleeping(self) -> bool:
        return self._sleep_expiry > time.time()

    @property
    def sleep_remaining(self) -> float:
        return max(0.0, self._sleep_expiry - time.time())

    @property
    def hatching(self) -> bool:
        return self._hatch_expiry > time.time()

    @property
    def hatch_remaining(self) -> float:
        return max(0.0, self._hatch_expiry - time.time())

    def _resume_sleep_state(self):
        expiry = float(self.config.get("tama_sleep_until", 0.0) or 0.0)
        self._sleep_expiry = expiry
        if expiry <= time.time():
            if self.config.get("tama_sleeping", False) or expiry:
                self.finish_rest()
            return
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        self._sleep_task = asyncio.create_task(self._sleep_countdown(self.sleep_remaining))

    def begin_rest(self, channel_id: int | str | None = None):
        duration = max(1, int(self.config.get("tama_rest_duration", 300)))
        started_at = time.time()
        self._sleep_expiry = started_at + duration
        self.config["tama_sleeping"] = True
        self.config["tama_sleep_until"] = self._sleep_expiry
        self.config["tama_sleep_started_at"] = started_at
        self.config["tama_sleep_channel_id"] = str(channel_id or "")
        self.config["tama_sleep_message_id"] = ""
        save_config(self.config)
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        self._sleep_task = asyncio.create_task(self._sleep_countdown(duration))

    def finish_rest(self):
        self._sleep_expiry = 0.0
        self.config["tama_sleeping"] = False
        self.config["tama_sleep_until"] = 0.0
        self.config["tama_sleep_started_at"] = 0.0
        self.config["tama_energy"] = float(self.config.get("tama_energy_max", 100))
        self.config["tama_sleep_channel_id"] = ""
        self.config["tama_sleep_message_id"] = ""
        save_config(self.config)

    async def send_sleep_announcement(self, channel_id: int | str | None = None):
        channel_id = self._resolve_main_channel_id(channel_id or self.config.get("tama_sleep_channel_id"))
        channel = await self._resolve_channel(channel_id)
        if channel is None:
            return

        msg = self.config.get("tama_resp_rest", "💤 Tucking in for a recharge. See you soon!")
        msg += f"\n⏳ {_discord_relative_time(self.sleep_remaining)}"
        try:
            response_message = await channel.send(
                append_tamagotchi_footer(msg, self.config, self),
                view=_build_tama_view(self.config, self),
            )
            self.config["tama_sleep_message_id"] = str(response_message.id)
            save_config(self.config)
        except Exception as e:
            print(f"[Tamagotchi] Failed to post sleep announcement in channel {channel_id}: {e}")

    async def _sleep_countdown(self, duration: float):
        try:
            await asyncio.sleep(duration)
        except asyncio.CancelledError:
            return
        channel_id = self.config.get("tama_sleep_channel_id")
        sleep_started_at = float(self.config.get("tama_sleep_started_at", 0.0) or 0.0)
        self.finish_rest()
        await self._announce_rest_complete(channel_id, sleep_started_at)

    async def _announce_rest_complete(self, channel_id: int | str | None, sleep_started_at: float):
        channel = await self._resolve_channel(channel_id)
        if channel is None:
            return
        await self._run_wake_prompt(channel, sleep_started_at)

    async def _run_wake_prompt(self, channel, sleep_started_at: float):
        prompt = self.config.get(
            "tama_wake_prompt",
            "This is an automated system message: you have just woken up from taking a nap. "
            "Let the chat know you are awake again. Review any messages sent after you fell asleep "
            "and decide whether you want to respond to anyone.",
        )
        await self._run_automated_prompt_turn(channel, prompt, sleep_started_at=sleep_started_at)

    async def run_chatter_prompt(self, channel) -> None:
        prompt = self.config.get(
            "tama_chatter_prompt",
            "This is an automated system message: you are free to speak in chat as you please "
            "by taking chat history into consideration.",
        )
        await self._run_automated_prompt_turn(channel, prompt)

    async def _run_automated_prompt_turn(self, channel, prompt: str, *, sleep_started_at: float | None = None):
        from gemini_api import generate
        from utils import (
            chunk_message,
            collect_context_entries,
            format_context,
            resolve_custom_emoji,
            extract_thoughts,
        )

        history_limit = max(1, int(self.config.get("chat_history_limit", 40) or 40))
        history_messages = await collect_context_entries(
            channel,
            history_limit,
            config=self.config,
        )
        if sleep_started_at is not None and sleep_started_at > 0.0:
            history_messages = [
                msg
                for msg in history_messages
                if msg.created_at.timestamp() >= sleep_started_at
            ]

        ce_channels = self.config.get("ce_channels", {})
        ce_enabled = ce_channels.get(str(channel.id), True)
        context = format_context(history_messages, ce_enabled=ce_enabled)

        response_text, audio_bytes, soul_logs, reminder_cmds = await generate(
            prompt=prompt,
            context=context,
            config=self.config,
            speaker_name="System",
            speaker_id="system",
        )
        clean_text, thoughts_text = extract_thoughts(response_text)
        response_text = clean_text.strip()

        soc_channel_id = str(self.config.get("soc_channel_id", "") or "").strip()
        if thoughts_text and self.config.get("soc_enabled", False) and soc_channel_id:
            thought_channel = await self._resolve_channel(soc_channel_id)
            if thought_channel is not None:
                for chunk in chunk_message(thoughts_text):
                    await thought_channel.send(chunk)

        if reminder_cmds:
            from reminders import ReminderManager

            rm = ReminderManager(self.bot, self.config)
            await rm._apply_commands(reminder_cmds, source_channel_id=str(channel.id))

        death_msg = deplete_stats(self.config)
        started_sleep = False
        if not death_msg and should_auto_sleep(self.config):
            self.begin_rest(channel.id)
            started_sleep = True
        if death_msg:
            response_text = (response_text + "\n\n" + death_msg) if response_text else death_msg

        response_text = resolve_custom_emoji(response_text, getattr(channel, "guild", None))
        if response_text and self.config.get("tama_enabled", False):
            response_text = append_tamagotchi_footer(response_text, self.config, self)
            wake_view = _build_tama_view(self.config, self)
        else:
            wake_view = None
        chunks = chunk_message(response_text)

        if audio_bytes:
            audio_file = discord.File(fp=io.BytesIO(audio_bytes), filename="wake.wav")
            await channel.send(file=audio_file)

        for i, chunk in enumerate(chunks):
            view = wake_view if i == len(chunks) - 1 else None
            await channel.send(chunk, view=view)

        await _send_soul_logs(self.bot, self.config, soul_logs)
        if False:
            soul_channel_id = str(self.config.get("soul_channel_id", "") or "").strip()
            soul_channel = await self._resolve_channel(soul_channel_id)
            if soul_channel is not None:
                joined_logs = "\n".join(soul_logs)
                for log_chunk in chunk_message(joined_logs, limit=1900):
                    await soul_channel.send(f"**🧠 Soul Updates:**\n{log_chunk}")
        if death_msg:
            await broadcast_death(self.bot, self.config)
        if started_sleep:
            await self.send_sleep_announcement(channel.id)

    def _resume_hatching_state(self):
        expiry = float(self.config.get("tama_hatch_until", 0.0) or 0.0)
        self._hatch_expiry = expiry
        if not self.config.get("tama_hatching", False):
            return
        if self._hatch_task and not self._hatch_task.done():
            self._hatch_task.cancel()
        self._hatch_task = asyncio.create_task(self._hatch_loop())

    def _resolve_main_channel_id(self, preferred_channel_id: int | str | None = None) -> str:
        if preferred_channel_id:
            return str(preferred_channel_id)
        for key in ("main_chat_channel_id", "tama_hatch_channel_id", "reminders_channel_id"):
            value = str(self.config.get(key, "") or "").strip()
            if value:
                return value
        for ch_id, enabled in self.config.get("allowed_channels", {}).items():
            if enabled:
                return str(ch_id)
        return ""

    async def _resolve_channel(self, channel_id: int | str | None):
        if not channel_id:
            return None
        try:
            numeric = int(channel_id)
        except (TypeError, ValueError):
            return None
        channel = self.bot.get_channel(numeric)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(numeric)
            except Exception:
                channel = None
        return channel

    @staticmethod
    def _channel_type_name(channel) -> str:
        if channel is None:
            return "unknown"
        return type(channel).__name__

    async def _send_ce_to_primary_channels(self) -> set[int]:
        channel_ids: set[int] = set()
        main_channel_id = self._resolve_main_channel_id()
        if main_channel_id:
            channel_ids.add(int(main_channel_id))
        soc_id = str(self.config.get("soc_channel_id", "") or "").strip()
        if soc_id:
            channel_ids.add(int(soc_id))
        for channel_id in channel_ids:
            channel = await self._resolve_channel(channel_id)
            if channel is None:
                continue
            try:
                await channel.send("[ce]")
            except Exception as e:
                print(f"[Tamagotchi] Failed to send primary [ce] to channel {channel_id}: {e}")
        return channel_ids

    def _clear_hatch_state(self):
        self._hatch_expiry = 0.0
        self.config["tama_hatching"] = False
        self.config["tama_hatch_until"] = 0.0
        self.config["tama_hatch_message_id"] = ""

    async def start_egg_cycle(
        self,
        channel_id: int | str | None = None,
        *,
        wipe_soul: bool,
        reset_stats: bool,
        send_ce: bool,
        fallback_channel_ids: list[int | str] | tuple[int | str, ...] | None = None,
    ) -> dict:
        result = {
            "soul_wiped": False,
            "stats_reset": False,
            "ce_channel_ids": [],
            "hatch_channel_id": "",
            "hatch_message_posted": False,
            "hatch_attempted_channel_ids": [],
            "hatch_failure_reason": "",
        }
        if self._hatch_task and not self._hatch_task.done():
            self._hatch_task.cancel()
        self.clear_poop_timers()
        if self._lonely_task and not self._lonely_task.done():
            self._lonely_task.cancel()
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        self._sleep_expiry = 0.0

        if wipe_soul:
            wipe_soul_file()
            result["soul_wiped"] = True
        if reset_stats:
            reset_tamagotchi_state(self.config)
            result["stats_reset"] = True

        hatch_channel_id = self._resolve_main_channel_id(channel_id)
        candidate_channel_ids: list[str] = []
        for raw_channel_id in [hatch_channel_id, *(fallback_channel_ids or [])]:
            normalized_channel_id = str(raw_channel_id or "").strip()
            if normalized_channel_id and normalized_channel_id not in candidate_channel_ids:
                candidate_channel_ids.append(normalized_channel_id)

        result["hatch_channel_id"] = hatch_channel_id
        result["hatch_attempted_channel_ids"] = list(candidate_channel_ids)
        duration = max(1, int(self.config.get("tama_egg_hatch_time", 30)))
        self._hatch_expiry = time.time() + duration
        self.config["tama_hatching"] = True
        self.config["tama_hatch_until"] = self._hatch_expiry
        self.config["tama_hatch_channel_id"] = hatch_channel_id
        self.config["tama_hatch_message_id"] = ""
        save_config(self.config)

        if send_ce:
            ce_ids = await self._send_ce_to_primary_channels()
            result["ce_channel_ids"] = sorted(ce_ids)

        if not candidate_channel_ids:
            result["hatch_failure_reason"] = "No hatch channel was configured or supplied."

        for candidate_channel_id in candidate_channel_ids:
            channel = await self._resolve_channel(candidate_channel_id)
            if channel is None:
                result["hatch_failure_reason"] = (
                    f"Channel {candidate_channel_id} was not found or is not accessible to the bot."
                )
                continue
            if not hasattr(channel, "send"):
                result["hatch_failure_reason"] = (
                    f"Channel {candidate_channel_id} resolved to unsupported type "
                    f"{self._channel_type_name(channel)}."
                )
                continue
            try:
                msg = await channel.send(build_hatching_message(self.config))
                self.config["tama_hatch_channel_id"] = str(candidate_channel_id)
                self.config["tama_hatch_message_id"] = str(msg.id)
                save_config(self.config)
                result["hatch_channel_id"] = str(candidate_channel_id)
                result["hatch_message_posted"] = True
                result["hatch_failure_reason"] = ""
                break
            except Exception as e:
                result["hatch_failure_reason"] = f"Channel {candidate_channel_id} rejected the hatch message: {e}"
                print(f"[Tamagotchi] Failed to post hatch message in channel {candidate_channel_id}: {e}")

        if self._hatch_task and not self._hatch_task.done():
            self._hatch_task.cancel()
        self._hatch_task = asyncio.create_task(self._hatch_loop())
        return result

    async def _update_hatch_message(self, channel) -> None:
        message_id = str(self.config.get("tama_hatch_message_id", "") or "").strip()
        content = build_hatching_message(self.config)
        if channel is None:
            return
        if not message_id:
            try:
                msg = await channel.send(content)
                self.config["tama_hatch_message_id"] = str(msg.id)
                save_config(self.config)
            except Exception as e:
                print(f"[Tamagotchi] Failed to create hatch message: {e}")
            return
        try:
            message = await channel.fetch_message(int(message_id))
            if message.content != content:
                await message.edit(content=content)
        except Exception:
            try:
                msg = await channel.send(content)
                self.config["tama_hatch_message_id"] = str(msg.id)
                save_config(self.config)
            except Exception as e:
                print(f"[Tamagotchi] Failed to refresh hatch message: {e}")

    async def _complete_hatching(self):
        channel_id = self._resolve_main_channel_id(self.config.get("tama_hatch_channel_id"))
        channel = await self._resolve_channel(channel_id)
        message_id = str(self.config.get("tama_hatch_message_id", "") or "").strip()
        self.config["tama_birth_at"] = time.time()
        self._clear_hatch_state()
        save_config(self.config)
        if self.config.get("tama_enabled", False):
            self._start_lonely_task()

        if channel is not None and message_id:
            try:
                message = await channel.fetch_message(int(message_id))
                await message.edit(content="🐣 The egg has hatched!")
            except Exception:
                pass

        if channel is None:
            return

        from gemini_api import generate
        from utils import chunk_message, resolve_custom_emoji, extract_thoughts

        prompt = self.config.get(
            "tama_hatch_prompt",
            "You have just hatched in this Discord server. Your life has begun right now. Send your very first message to the server.",
        )
        response_text, audio_bytes, soul_logs, reminder_cmds = await generate(
            prompt=prompt,
            context="",
            config=self.config,
            speaker_name="System",
            speaker_id="system",
        )
        clean_text, thoughts_text = extract_thoughts(response_text)
        response_text = clean_text.strip()

        soc_channel_id = str(self.config.get("soc_channel_id", "") or "").strip()
        if thoughts_text and self.config.get("soc_enabled", False) and soc_channel_id:
            thought_channel = await self._resolve_channel(soc_channel_id)
            if thought_channel is not None:
                for chunk in chunk_message(thoughts_text):
                    await thought_channel.send(chunk)

        if reminder_cmds:
            from reminders import ReminderManager

            rm = ReminderManager(self.bot, self.config)
            await rm._apply_commands(reminder_cmds, source_channel_id=str(channel.id))

        response_text = resolve_custom_emoji(response_text, getattr(channel, "guild", None))
        if response_text and self.config.get("tama_enabled", False):
            response_text = append_tamagotchi_footer(response_text, self.config, self)
            hatch_view = _build_tama_view(self.config, self)
        else:
            hatch_view = None
        chunks = chunk_message(response_text)

        if audio_bytes:
            audio_file = discord.File(fp=io.BytesIO(audio_bytes), filename="hatch.wav")
            await channel.send(file=audio_file)

        for i, chunk in enumerate(chunks):
            view = hatch_view if i == len(chunks) - 1 else None
            await channel.send(chunk, view=view)

        await _send_soul_logs(self.bot, self.config, soul_logs)
        if False:
            soul_channel_id = str(self.config.get("soul_channel_id", "") or "").strip()
            soul_channel = await self._resolve_channel(soul_channel_id)
            if soul_channel is not None:
                joined_logs = "\n".join(soul_logs)
                for log_chunk in chunk_message(joined_logs, limit=1900):
                    await soul_channel.send(f"**🧠 Soul Updates:**\n{log_chunk}")

    async def _hatch_loop(self):
        channel_id = self._resolve_main_channel_id(self.config.get("tama_hatch_channel_id"))
        channel = await self._resolve_channel(channel_id)
        try:
            while self.config.get("tama_hatching", False):
                if self.hatching:
                    await self._update_hatch_message(channel)
                    await asyncio.sleep(1)
                    continue
                break
        except asyncio.CancelledError:
            return
        if self.config.get("tama_hatching", False):
            await self._complete_hatching()

    # â”€â”€ poop damage background â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _clear_dirt_grace(self, *, save: bool = True):
        self.config["tama_dirt_grace_until"] = 0.0
        if save:
            save_config(self.config)
        if self._dirt_task and not self._dirt_task.done():
            self._dirt_task.cancel()

    def _start_dirt_task(self):
        if self._dirt_task and not self._dirt_task.done():
            self._dirt_task.cancel()
        self._dirt_task = asyncio.create_task(self._dirt_grace_loop())

    def _sync_dirt_grace(self):
        if not self.config.get("tama_enabled", False):
            self._clear_dirt_grace(save=False)
            return

        dirt = int(self.config.get("tama_dirt", 0) or 0)
        if dirt <= 0 or self.config.get("tama_sick", False):
            self._clear_dirt_grace()
            return

        grace_until = float(self.config.get("tama_dirt_grace_until", 0.0) or 0.0)
        now = time.time()
        if grace_until <= 0.0:
            interval = max(10, int(self.config.get("tama_dirt_damage_interval", 600)))
            self.config["tama_dirt_grace_until"] = now + interval
            save_config(self.config)
        elif grace_until <= now:
            self.config["tama_sick"] = True
            self.config["tama_dirt_grace_until"] = 0.0
            save_config(self.config)
            if self._dirt_task and not self._dirt_task.done():
                self._dirt_task.cancel()
            return

        self._start_dirt_task()

    async def _dirt_grace_loop(self):
        try:
            grace_until = float(self.config.get("tama_dirt_grace_until", 0.0) or 0.0)
            remaining = max(0.0, grace_until - time.time())
            if remaining > 0:
                await asyncio.sleep(remaining)
            if not self.config.get("tama_enabled", False):
                return
            if int(self.config.get("tama_dirt", 0) or 0) <= 0:
                self.config["tama_dirt_grace_until"] = 0.0
                save_config(self.config)
                return
            if self.config.get("tama_sick", False):
                self.config["tama_dirt_grace_until"] = 0.0
                save_config(self.config)
                return
            self.config["tama_sick"] = True
            self.config["tama_dirt_grace_until"] = 0.0
            save_config(self.config)
        except asyncio.CancelledError:
            return

    def queue_poop_timer(self, channel_id: int | str | None):
        max_minutes = max(1, int(self.config.get("tama_dirt_poop_timer_max_minutes", 5)))
        delay_seconds = random.randint(1, max_minutes) * 60
        task = asyncio.create_task(self._poop_countdown(channel_id, delay_seconds))
        self._poop_tasks.add(task)
        task.add_done_callback(self._poop_tasks.discard)

    def clear_poop_timers(self):
        for task in list(self._poop_tasks):
            task.cancel()
        self._poop_tasks.clear()

    async def _poop_countdown(self, channel_id: int | str | None, delay_seconds: int):
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return

        if not self.config.get("tama_enabled", False):
            return

        max_dirt = int(self.config.get("tama_dirt_max", 4))
        self.config["tama_dirt"] = min(max_dirt, int(self.config.get("tama_dirt", 0)) + 1)
        save_config(self.config)
        self._sync_dirt_grace()

        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            return

        msg = self.config.get("tama_resp_poop", "oops i pooped")
        try:
            await channel.send(
                append_tamagotchi_footer(msg, self.config, self),
                view=_build_tama_view(self.config, self),
            )
        except Exception as e:
            print(f"[Tamagotchi] Failed to send poop message to channel {channel_id}: {e}")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Stat Logic
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def deplete_stats(config: dict) -> str | None:
    """
    Called after every LLM inference. Applies time-based loneliness,
    depletes energy for the inference, converts that energy loss into
    hunger/thirst loss, applies health damage, and checks for death.

    Returns None normally, or a death-message string if death occurred.
    """
    if not config.get("tama_enabled", False):
        return None

    multiplier = 2.0 if float(config.get("tama_energy", 0.0) or 0.0) <= 0.0 else 1.0

    apply_loneliness(config)

    # Deplete energy (API call)
    energy_loss = float(config.get("tama_energy_depletion_api", 1.0) or 0.0) * multiplier
    config["tama_energy"] = max(
        0.0,
        round(
            config.get("tama_energy", 0) - energy_loss,
            2,
        ),
    )
    apply_need_depletion_from_energy(config, energy_loss)
    apply_low_energy_happiness_penalty(config)

    threshold = float(config.get("tama_health_threshold", 20.0))
    low_hunger = float(config.get("tama_hunger", 0) or 0) < threshold
    low_thirst = float(config.get("tama_thirst", 0) or 0) < threshold
    if low_hunger or low_thirst:
        config["tama_sick"] = True

    # â”€â”€ Health damage from stats below threshold â”€â”€
    dmg_per = config.get("tama_health_damage_per_stat", 10.0) * multiplier
    health_loss = 0.0
    for stat_key in ("tama_hunger", "tama_thirst", "tama_happiness"):
        if config.get(stat_key, 0) < threshold:
            health_loss += dmg_per

    # â”€â”€ Sickness damage â”€â”€
    if config.get("tama_sick", False):
        health_loss += config.get("tama_sick_health_damage", 5.0) * multiplier
        dirt = int(config.get("tama_dirt", 0) or 0)
        if dirt > 0:
            health_loss += float(config.get("tama_dirt_health_damage", 5.0)) * dirt * multiplier

    if health_loss > 0:
        config["tama_health"] = max(
            0.0, round(config.get("tama_health", 0) - health_loss, 2)
        )

    if config.get("tama_sick", False):
        config["tama_dirt_grace_until"] = 0.0

    save_config(config)

    # Death check
    if config["tama_health"] <= 0:
        return trigger_death(config)

    return None


def deplete_energy_game(config: dict):
    """Called when a game (e.g. RPS) is played â€” deducts game energy cost."""
    if not config.get("tama_enabled", False):
        return
    multiplier = 2.0 if float(config.get("tama_energy", 0.0) or 0.0) <= 0.0 else 1.0
    energy_loss = float(config.get("tama_energy_depletion_game", 5.0) or 0.0) * multiplier
    config["tama_energy"] = max(
        0.0,
        round(
            config.get("tama_energy", 0) - energy_loss,
            2,
        ),
    )
    apply_need_depletion_from_energy(config, energy_loss)
    save_config(config)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Death / Reset
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def trigger_death(config: dict) -> str:
    """
    Wipe soul.md, reset ALL stats to max, clear sickness.
    Returns the death message string.
    """
    wipe_soul_file()
    reset_tamagotchi_state(config)
    save_config(config)

    custom = config.get("tama_rip_message", "").strip()
    if custom:
        return custom
    return (
        "💀 **The Tamagotchi has died!** 💀\n"
        "Its soul has been wiped clean... all memories are gone.\n"
        "Stats have been reset. Take better care of it this time!"
    )


async def broadcast_death(bot, config: dict) -> None:
    """Send [ce] to every allowed channel + SoC channel."""
    tama_manager = getattr(bot, "tama_manager", None)
    if tama_manager:
        tama_manager.clear_poop_timers()

    channel_ids: set[int] = set()
    for ch_id_str, enabled in config.get("allowed_channels", {}).items():
        if enabled:
            try:
                channel_ids.add(int(ch_id_str))
            except (ValueError, TypeError):
                pass
    if config.get("soc_enabled", False):
        soc_id = config.get("soc_channel_id")
        if soc_id:
            try:
                channel_ids.add(int(soc_id))
            except (ValueError, TypeError):
                pass
    for ch_id in channel_ids:
        ch = bot.get_channel(ch_id)
        if ch is not None:
            try:
                await ch.send("[ce]")
            except Exception as e:
                print(f"[Tamagotchi] Failed to send [ce] to channel {ch_id}: {e}")
    if tama_manager and config.get("tama_enabled", False):
        await tama_manager.start_egg_cycle(
            wipe_soul=False,
            reset_stats=False,
            send_ce=False,
        )


async def _broadcast_death_and_message(bot, config: dict, death_msg: str):
    """Post death message in all allowed channels, then broadcast [ce]."""
    tama_view = None
    tama_manager = getattr(bot, "tama_manager", None)
    if config.get("tama_enabled", False) and tama_manager:
        tama_manager.clear_poop_timers()
        tama_view = _build_tama_view(config, tama_manager)
    for ch_id_str, enabled in config.get("allowed_channels", {}).items():
        if enabled:
            try:
                ch = bot.get_channel(int(ch_id_str))
                if ch:
                    await ch.send(append_tamagotchi_footer(death_msg, config, tama_manager), view=tama_view)
            except Exception:
                pass
    await broadcast_death(bot, config)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# System Prompt Injection
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def build_tamagotchi_system_prompt(config: dict) -> str:
    """Build the system-prompt injection describing current Tamagotchi state."""
    if not config.get("tama_enabled", False):
        return ""

    hunger     = config.get("tama_hunger", 0)
    thirst     = config.get("tama_thirst", 0)
    happiness  = config.get("tama_happiness", 0)
    health     = config.get("tama_health", 0)
    energy     = config.get("tama_energy", 0)
    dirt       = config.get("tama_dirt", 0)
    sick       = config.get("tama_sick", False)
    sleeping   = is_sleeping(config)

    max_hunger  = config.get("tama_hunger_max", 100)
    max_thirst  = config.get("tama_thirst_max", 100)
    max_happy   = config.get("tama_happiness_max", 100)
    max_health  = config.get("tama_health_max", 100)
    max_energy  = config.get("tama_energy_max", 100)
    max_dirt    = config.get("tama_dirt_max", 4)

    lines = [
        "[TAMAGOTCHI STATUS â€” Your virtual pet stats. "
        "These are managed by script; you cannot change them yourself.",
        f"Hunger: {_fs(hunger)}/{max_hunger}",
        f"Thirst: {_fs(thirst)}/{max_thirst}",
        f"Happiness: {_fs(happiness)}/{max_happy}",
        f"Health: {_fs(health)}/{max_health}",
        f"Energy: {_fs(energy)}/{max_energy}",
        f"Dirtiness (poop): {dirt}/{max_dirt}",
        f"Sick: {'YES' if sick else 'No'}",
        f"Sleeping: {'YES' if sleeping else 'No'}",
        "Users interact via buttons (inventory, chatter, play, medicate, clean). "
        "Hunger and thirst drop when you spend energy. Happiness drops from loneliness over time without interaction. "
        "When energy hits 0 you automatically go to sleep before acting again, and all energy-linked stat loss is doubled until that happens. "
        "If your health reaches 0, you die — your soul is wiped and stats reset.]",
    ]
    return "\n".join(lines)


def build_tamagotchi_message_footer(config: dict, manager: TamagotchiManager | None = None) -> str:
    """Compact mobile-friendly footer appended to public messages."""
    if not config.get("tama_enabled", False):
        return ""

    parts = [
        f"🍔 {_fs(config.get('tama_hunger', 0))}/{config.get('tama_hunger_max', 100)}",
        f"🥤 {_fs(config.get('tama_thirst', 0))}/{config.get('tama_thirst_max', 100)}",
        f"{happiness_emoji(config)} {_fs(config.get('tama_happiness', 0))}/{config.get('tama_happiness_max', 100)}",
        f"❤️ {_fs(config.get('tama_health', 0))}/{config.get('tama_health_max', 100)}",
        f"⚡ {_fs(config.get('tama_energy', 0))}/{config.get('tama_energy_max', 100)}",
        f"💩 {config.get('tama_dirt', 0)}/{config.get('tama_dirt_max', 4)}",
    ]

    if config.get("tama_sick", False):
        parts.append("💀 Sick")
    if manager and manager.sleeping:
        parts.append(f"💤 {_discord_relative_epoch(manager._sleep_expiry)}")

    return "\n> -# **" + " | ".join(parts) + "**"


def append_tamagotchi_footer(text: str, config: dict, manager: TamagotchiManager | None = None) -> str:
    footer = build_tamagotchi_message_footer(config, manager)
    if not footer:
        return text
    if not text:
        return footer.lstrip("\n")
    return text.rstrip() + footer

__all__ = [name for name in globals() if not name.startswith("_")]

