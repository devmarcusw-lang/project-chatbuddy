"""Shared stat and state helpers for the Tamagotchi feature."""

from .common import *
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Helpers
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _fs(val: float) -> str:
    """Format a stat value: integer if whole, else up to 2 decimals."""
    if val == int(val):
        return str(int(val))
    return f"{val:.2f}".rstrip("0").rstrip(".")


def _fmt_countdown(seconds: float) -> str:
    """Return a human-readable countdown string like '4m 32s'."""
    s = max(0, int(seconds))
    if s >= 60:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s}s"


def _discord_relative_time(seconds: float) -> str:
    target = int(time.time() + max(0.0, seconds))
    return f"<t:{target}:R>"


def _discord_relative_epoch(epoch: float) -> str:
    return f"<t:{max(0, int(epoch))}:R>"


def _bot_display_name(interaction: discord.Interaction) -> str:
    guild_me = getattr(interaction.guild, "me", None)
    if guild_me is not None:
        display_name = getattr(guild_me, "display_name", "") or getattr(guild_me, "name", "")
        if display_name:
            return display_name

    client_user = getattr(interaction.client, "user", None)
    if client_user is not None:
        display_name = getattr(client_user, "display_name", "") or getattr(client_user, "name", "")
        if display_name:
            return display_name

    return "Botty"


def _log_tamagotchi_action(
    config: dict,
    interaction: discord.Interaction,
    action: str,
    message_id: int,
    *,
    item_id: str = "",
    item_name: str = "",
    item_emoji: str = "",
) -> None:
    action_log = list(config.get("tama_action_log", []))
    action_log.append(
        {
            "action": action,
            "channel_id": str(interaction.channel_id or ""),
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.display_name,
            "message_id": str(message_id),
            "timestamp": time.time(),
            "item_id": item_id,
            "item_name": item_name,
            "item_emoji": item_emoji,
        }
    )
    config["tama_action_log"] = action_log[-200:]
    save_config(config)


def _item_action_name(item: dict) -> str:
    if item.get("item_type") == "food":
        return "feed"
    if item.get("item_type") == "drink":
        return "drink"
    if item.get("item_type") == "misc":
        return "other"
    return ""


def _item_default_icon(action: str) -> str:
    return "🍔" if action == "feed" else "🥤"


def _apply_item_emoji_to_response(message: str, item: dict) -> str:
    action = _item_action_name(item)
    chosen_emoji = item.get("emoji", "").strip() or _item_default_icon(action)
    default_icon = _item_default_icon(action)
    if "{item}" in message:
        return message.replace("{item}", chosen_emoji)
    if default_icon in message:
        return message.replace(default_icon, chosen_emoji)
    if chosen_emoji in message:
        return message
    return f"{chosen_emoji} {message}".strip()


def is_sleeping(config: dict) -> bool:
    """Return True while the rest timer is active."""
    sleep_until = float(config.get("tama_sleep_until", 0.0) or 0.0)
    if sleep_until <= time.time():
        if config.get("tama_sleeping", False) or sleep_until:
            config["tama_sleeping"] = False
            config["tama_sleep_until"] = 0.0
            save_config(config)
        return False
    return True


def sleeping_remaining(config: dict) -> float:
    return max(0.0, float(config.get("tama_sleep_until", 0.0) or 0.0) - time.time())


def build_sleeping_message(config: dict) -> str:
    template = config.get("tama_resp_sleeping", "I am sleeping come back in {time}")
    return template.replace("{time}", _discord_relative_time(sleeping_remaining(config)))


def build_awake_message(config: dict) -> str:
    return "✨ I'm awake again!"


def is_hatching(config: dict) -> bool:
    hatch_until = float(config.get("tama_hatch_until", 0.0) or 0.0)
    return bool(config.get("tama_hatching", False)) and hatch_until > time.time()


def hatching_remaining(config: dict) -> float:
    return max(0.0, float(config.get("tama_hatch_until", 0.0) or 0.0) - time.time())


def build_hatching_message(config: dict) -> str:
    remaining = max(1, int(hatching_remaining(config) + 0.999))
    return f"🥚 I'm about to hatch... life begins in **{remaining}s**. Please wait for me to hatch first."


def can_use_energy(config: dict) -> bool:
    return float(config.get("tama_energy", 0.0) or 0.0) > 0.0


def energy_ratio(config: dict) -> float:
    maximum = float(config.get("tama_energy_max", 100) or 0.0)
    if maximum <= 0.0:
        return 0.0
    current = float(config.get("tama_energy", 0.0) or 0.0)
    return max(0.0, min(1.0, current / maximum))


def should_auto_sleep(config: dict) -> bool:
    return (
        config.get("tama_enabled", False)
        and not is_sleeping(config)
        and float(config.get("tama_energy", 0.0) or 0.0) <= 0.0
    )


def apply_low_energy_happiness_penalty(config: dict) -> float:
    threshold_pct = max(0.0, min(100.0, float(config.get("tama_low_energy_happiness_threshold_pct", 10.0) or 0.0)))
    happiness_loss = max(0.0, float(config.get("tama_low_energy_happiness_loss", 1.0) or 0.0))
    if threshold_pct <= 0.0 or happiness_loss <= 0.0:
        return 0.0
    if energy_ratio(config) * 100.0 >= threshold_pct:
        return 0.0

    current_happiness = float(config.get("tama_happiness", 0.0) or 0.0)
    new_happiness = max(0.0, round(current_happiness - happiness_loss, 2))
    actual_loss = round(current_happiness - new_happiness, 2)
    if actual_loss > 0.0:
        config["tama_happiness"] = new_happiness
    return actual_loss


def _stat_ratio(current: float, maximum: float) -> float:
    if maximum <= 0:
        return 0.0
    return max(0.0, min(1.0, float(current) / float(maximum)))


def happiness_emoji(config: dict) -> str:
    percent = _stat_ratio(
        float(config.get("tama_happiness", 0)),
        float(config.get("tama_happiness_max", 100)),
    ) * 100
    if percent >= 80:
        return "😁"
    if percent >= 60:
        return "😀"
    if percent >= 40:
        return "🙂"
    if percent >= 20:
        return "😕"
    return "😠"


def should_show_medicate(config: dict) -> bool:
    current_health = float(config.get("tama_health", 0.0) or 0.0)
    max_health = float(config.get("tama_health_max", 100.0) or 100.0)
    return bool(config.get("tama_sick", False)) or current_health < max_health


def wipe_soul_file() -> None:
    try:
        with open("soul.md", "w", encoding="utf-8") as f:
            f.write("{}")
        print("[Tamagotchi] soul.md wiped.")
    except Exception as e:
        print(f"[Tamagotchi] Failed to wipe soul.md: {e}")


def reset_tamagotchi_state(config: dict) -> None:
    now = time.time()
    config["tama_hunger"] = round(float(config.get("tama_hunger_max", 100)) * 0.5, 2)
    config["tama_thirst"] = round(float(config.get("tama_thirst_max", 100)) * 0.5, 2)
    config["tama_happiness"] = round(float(config.get("tama_happiness_max", 100)) * 0.5, 2)
    config["tama_health"] = float(config.get("tama_health_max", 100))
    config["tama_energy"] = float(config.get("tama_energy_max", 100))
    config["tama_dirt"] = 0
    config["tama_dirt_food_counter"] = 0
    config["tama_dirt_grace_until"] = 0.0
    config["tama_feed_energy_counter"] = 0
    config["tama_drink_energy_counter"] = 0
    config["tama_sick"] = False
    config["tama_sleeping"] = False
    config["tama_sleep_until"] = 0.0
    config["tama_last_interaction_at"] = now
    config["tama_lonely_last_update_at"] = now


def apply_loneliness(config: dict, *, now: float | None = None, save: bool = False) -> float:
    if not config.get("tama_enabled", False):
        return 0.0

    now = time.time() if now is None else now
    interval = max(1.0, float(config.get("tama_happiness_depletion_interval", 600) or 600))
    amount = max(0.0, float(config.get("tama_happiness_depletion", 1.0) or 0.0))
    last_interaction = float(config.get("tama_last_interaction_at", 0.0) or 0.0)
    last_update = float(config.get("tama_lonely_last_update_at", 0.0) or 0.0)
    base = max(last_interaction, last_update)

    if base <= 0.0:
        config["tama_last_interaction_at"] = now
        config["tama_lonely_last_update_at"] = now
        if save:
            save_config(config)
        return 0.0

    steps = int(max(0.0, now - base) // interval)
    if steps <= 0 or amount <= 0.0:
        return 0.0

    loss = round(steps * amount, 2)
    config["tama_happiness"] = max(
        0.0,
        round(float(config.get("tama_happiness", 0.0) or 0.0) - loss, 2),
    )
    config["tama_lonely_last_update_at"] = base + (steps * interval)
    if save:
        save_config(config)
    return loss


def apply_need_depletion_from_energy(config: dict, energy_loss: float) -> None:
    if not config.get("tama_enabled", False):
        return

    energy_loss = max(0.0, float(energy_loss or 0.0))
    if energy_loss <= 0.0:
        return

    per_energy = max(0.01, float(config.get("tama_needs_depletion_per_energy", 1.0) or 1.0))
    hunger_loss = (energy_loss / per_energy) * max(0.0, float(config.get("tama_hunger_depletion", 1.0) or 0.0))
    thirst_loss = (energy_loss / per_energy) * max(0.0, float(config.get("tama_thirst_depletion", 1.0) or 0.0))

    config["tama_hunger"] = max(
        0.0,
        round(float(config.get("tama_hunger", 0.0) or 0.0) - hunger_loss, 2),
    )
    config["tama_thirst"] = max(
        0.0,
        round(float(config.get("tama_thirst", 0.0) or 0.0) - thirst_loss, 2),
    )

__all__ = [name for name in globals() if not name.startswith("__")]

