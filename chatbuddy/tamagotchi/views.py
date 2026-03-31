"""Discord UI for the Tamagotchi feature."""

from .common import *
from .runtime import *
from .state import *
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Discord UI â€” Stat Display Buttons (grey, non-interactive)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TamagotchiView(ui.View):
    """
    Persistent view with stat display (grey buttons) + action buttons.
    Attached to every bot response when tama_enabled is True.
    """

    def __init__(self, config: dict, manager: TamagotchiManager):
        # timeout=None makes the view persistent
        super().__init__(timeout=None)
        self.config = config
        self.manager = manager
        self._build()

    def _build(self):
        # â”€â”€ Row 0: Action buttons only â”€â”€
        self.add_item(InventoryButton(self.config, self.manager))
        if self.config.get("tama_chatter_enabled", True):
            self.add_item(ChatterButton(self.config, self.manager))
        self.add_item(PlayButton(self.config, self.manager))
        if should_show_medicate(self.config):
            self.add_item(MedicateButton(self.config, self.manager))
        if int(self.config.get("tama_dirt", 0) or 0) > 0:
            self.add_item(CleanButton(self.config, self.manager))


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Action Buttons
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def _send_sleep_block(interaction: discord.Interaction, config: dict):
    await interaction.response.send_message(build_sleeping_message(config), ephemeral=True)


def _no_energy_message(config: dict) -> str:
    return config.get("tama_resp_no_energy", "⚡ I'm out of energy and need a rest first!")


def _interaction_actor_name(interaction: discord.Interaction) -> str:
    return _actor_display_name(interaction.user)


def _public_action_message(
    interaction: discord.Interaction,
    message: str,
    *,
    action_summary: str,
    item: dict | None = None,
) -> str:
    bot_name = _bot_display_name(interaction)
    actor_name = _interaction_actor_name(interaction)
    return render_tamagotchi_action_message(
        message,
        actor_name=actor_name,
        action_summary=action_summary.format(bot_name=bot_name),
        bot_name=bot_name,
        item_name=item.get("name", "") if item else "",
        item_emoji=item.get("emoji", "") if item else "",
    )


def _lucky_gift_pool(config: dict) -> list[dict]:
    return [item for item in get_inventory_items(config, visible_only=False) if item.get("lucky_gift_prize")]


def _lucky_gift_countdown_text(
    config: dict,
    giver_name: str,
    bot_name: str,
    seconds_remaining: float,
) -> str:
    return (
        "🎁 **Lucky Gift**\n"
        f"**{giver_name}** is opening a present for **{bot_name}**.\n"
        "The ribbon is rustling... something fun is hiding inside.\n"
        f"Reveal in **{max(1, int(seconds_remaining + 0.999))}s**."
    )


def _apply_lucky_gift_reward(config: dict, item: dict) -> tuple[float, float, int, bool]:
    items = config.setdefault("tama_inventory_items", {})
    item_entry = items.get(item["id"])
    stored_in_inventory = bool(item.get("store_in_inventory", True))
    if stored_in_inventory and isinstance(item_entry, dict):
        current_amount = _coerce_item_amount(item_entry.get("amount", 0))
        if current_amount >= 0:
            item_entry["amount"] = current_amount + 1

    happiness_delta = round(float(item.get("happiness_delta", 0.0) or 0.0), 2)
    energy_delta = round(float(item.get("energy_delta", 0.0) or 0.0), 2)
    if not stored_in_inventory and happiness_delta:
        max_happy = float(config.get("tama_happiness_max", 100))
        previous_happiness = float(config.get("tama_happiness", 0.0) or 0.0)
        new_happiness = min(
            max_happy,
            max(0.0, round(previous_happiness + happiness_delta, 2)),
        )
        config["tama_happiness"] = new_happiness
        happiness_delta = round(new_happiness - previous_happiness, 2)
    if not stored_in_inventory and energy_delta:
        energy_delta = apply_direct_energy_delta(config, energy_delta)
    save_config(config)
    awarded_amount = 1 if stored_in_inventory and not item.get("is_unlimited") else 0
    return happiness_delta, energy_delta, awarded_amount, stored_in_inventory


def _lucky_gift_reveal_text(
    giver_name: str,
    bot_name: str,
    item: dict,
    happiness_delta: float,
    energy_delta: float,
    stored_in_inventory: bool,
) -> str:
    parts = [
        "🎁 **Lucky Gift Opened!**",
        (
            f"**{giver_name}** gifted **{bot_name}** a lucky gift, "
            f"**{bot_name}** received {item.get('emoji', '🎁')} **{item.get('name', 'a prize')}**."
        ),
    ]
    if item.get("item_type") in {"food", "drink"} and float(item.get("multiplier", 0.0) or 0.0) > 0:
        parts.append(f"Fill multiplier: x{item.get('multiplier', 1.0)}.")
    if stored_in_inventory:
        parts.append(f"Added to **{bot_name}**'s inventory.")
    if energy_delta > 0:
        parts.append(f"Energy +{_fs(energy_delta)} {'applied now' if not stored_in_inventory else 'when used'}.")
    elif energy_delta < 0:
        parts.append(f"Energy {_fs(energy_delta)} {'applied now' if not stored_in_inventory else 'when used'}.")
    if happiness_delta > 0:
        parts.append(f"Happiness +{_fs(happiness_delta)} {'applied now' if not stored_in_inventory else 'when used'}.")
    elif happiness_delta < 0:
        parts.append(f"Happiness {_fs(happiness_delta)} {'applied now' if not stored_in_inventory else 'when used'}.")
    return "\n".join(parts)


async def _refresh_inventory_message(
    interaction: discord.Interaction,
    config: dict,
    manager: TamagotchiManager,
) -> None:
    if not interaction.message:
        return
    try:
        visible_items = get_inventory_items(config, visible_only=True)
        await interaction.message.edit(
            content=inventory_message_text(config),
            view=InventoryView(config, manager, owner_id=interaction.user.id) if visible_items else None,
        )
    except Exception:
        return


async def _consume_inventory_item(
    interaction: discord.Interaction,
    config: dict,
    manager: TamagotchiManager,
    item_id: str,
) -> None:
    manager.record_interaction()
    item = get_inventory_item(config, item_id)
    if not item or not (item["is_unlimited"] or item["amount"] > 0):
        await interaction.response.send_message("⚠️ That item is not in the inventory right now.", ephemeral=True)
        await _refresh_inventory_message(interaction, config, manager)
        return

    if manager.sleeping:
        await _send_sleep_block(interaction, config)
        return

    action = _item_action_name(item)
    remaining = manager.check_cooldown(action)
    if remaining > 0:
        msg = config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
            "{time}", _discord_relative_time(remaining)
        )
        await interaction.response.send_message(msg, ephemeral=True)
        return

    multiplier = max(0.0, float(item.get("multiplier", 1.0) or 0.0))

    if action == "feed":
        max_hunger = float(config.get("tama_hunger_max", 100))
        fill = float(config.get("tama_feed_amount", 10.0)) * multiplier
        config["tama_hunger"] = min(max_hunger, round(float(config.get("tama_hunger", 0)) + fill, 2))

        food_energy_counter = int(config.get("tama_feed_energy_counter", 0)) + 1
        food_energy_every = max(1, int(config.get("tama_feed_energy_every", 1)))
        config["tama_feed_energy_counter"] = food_energy_counter
        if food_energy_counter >= food_energy_every:
            config["tama_feed_energy_counter"] = 0
            energy_multiplier = max(0.0, float(item.get("energy_multiplier", 1.0) or 0.0))
            energy_gain = max(0.0, float(config.get("tama_feed_energy_gain", 1.0))) * energy_multiplier
            apply_direct_energy_delta(config, energy_gain)

        config["tama_dirt_food_counter"] = int(config.get("tama_dirt_food_counter", 0)) + 1
        poop_threshold = max(1, int(config.get("tama_dirt_food_threshold", 5)))
        while config["tama_dirt_food_counter"] >= poop_threshold:
            config["tama_dirt_food_counter"] -= poop_threshold
            manager.queue_poop_timer(interaction.channel_id)
        response_key = "tama_resp_feed"
        cooldown_key = "tama_cd_feed"
    else:
        if action == "drink":
            max_thirst = float(config.get("tama_thirst_max", 100))
            fill = float(config.get("tama_drink_amount", 10.0)) * multiplier
            config["tama_thirst"] = min(max_thirst, round(float(config.get("tama_thirst", 0)) + fill, 2))

            drink_energy_counter = int(config.get("tama_drink_energy_counter", 0)) + 1
            drink_energy_every = max(1, int(config.get("tama_drink_energy_every", 1)))
            config["tama_drink_energy_counter"] = drink_energy_counter
            if drink_energy_counter >= drink_energy_every:
                config["tama_drink_energy_counter"] = 0
                energy_multiplier = max(0.0, float(item.get("energy_multiplier", 1.0) or 0.0))
                energy_gain = max(0.0, float(config.get("tama_drink_energy_gain", 1.0))) * energy_multiplier
                apply_direct_energy_delta(config, energy_gain)
            response_key = "tama_resp_drink"
            cooldown_key = "tama_cd_drink"
        else:
            happiness_delta = round(float(item.get("happiness_delta", 0.0) or 0.0), 2)
            max_happy = float(config.get("tama_happiness_max", 100))
            config["tama_happiness"] = min(
                max_happy,
                max(0.0, round(float(config.get("tama_happiness", 0)) + happiness_delta, 2)),
            )
            response_key = None
            cooldown_key = "tama_cd_other"

    direct_energy_delta = apply_direct_energy_delta(config, float(item.get("energy_delta", 0.0) or 0.0))

    if not item["is_unlimited"]:
        config["tama_inventory_items"][item_id]["amount"] = max(0, item["amount"] - 1)

    save_config(config)
    manager.set_cooldown(action, int(config.get(cooldown_key, 60)))

    if action == "feed":
        default_response = "*nom nom* 🍔 Thanks for the food!"
        msg = config.get(response_key, default_response)
        msg = _apply_item_emoji_to_response(msg, item)
        msg = _public_action_message(
            interaction,
            msg,
            action_summary="fed **{bot_name}**",
            item=item,
        )
    elif action == "drink":
        default_response = "*gulp gulp* 🥤 That hit the spot!"
        msg = config.get(response_key, default_response)
        msg = _apply_item_emoji_to_response(msg, item)
        msg = _public_action_message(
            interaction,
            msg,
            action_summary="gave **{bot_name}** a drink",
            item=item,
        )
    else:
        happiness_delta = round(float(item.get("happiness_delta", 0.0) or 0.0), 2)
        msg = f"{item.get('emoji', '🎁')} Used **{item.get('name', 'item')}**."
        if direct_energy_delta > 0:
            msg += f"\n⚡ Energy +{_fs(direct_energy_delta)}."
        elif direct_energy_delta < 0:
            msg += f"\n⚡ Energy {_fs(direct_energy_delta)}."
        if happiness_delta > 0:
            msg += f"\n😊 Happiness +{_fs(happiness_delta)}."
        elif happiness_delta < 0:
            msg += f"\n☹️ Happiness {_fs(happiness_delta)}."
        msg = _public_action_message(
            interaction,
            msg,
            action_summary="used {item_emoji} **{item_name}** on **{bot_name}**".format(
                item_emoji=item.get("emoji", "🎁"),
                item_name=item.get("name", "item"),
                bot_name="{bot_name}",
            ),
            item=item,
        )
    await interaction.response.send_message(
        append_tamagotchi_footer(msg, config, manager),
        view=TamagotchiView(config, manager),
    )
    response_message = await interaction.original_response()
    _log_tamagotchi_action(
        config,
        interaction,
        action,
        response_message.id,
        item_id=item["id"],
        item_name=item["name"],
        item_emoji=item["emoji"],
    )
    await _refresh_inventory_message(interaction, config, manager)


class InventoryButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="Inventory",
            emoji="🎒",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_inventory",
            row=0,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        await interaction.response.send_message(
            inventory_message_text(self.config),
            ephemeral=True,
            view=InventoryView(self.config, self.manager, owner_id=interaction.user.id),
        )


class InventoryView(ui.View):
    def __init__(self, config: dict, manager: TamagotchiManager, owner_id: int):
        super().__init__(timeout=300)
        self.config = config
        self.manager = manager
        self.owner_id = owner_id
        self._build()

    def _build(self):
        visible_items = get_inventory_items(self.config, visible_only=True)
        for idx, item in enumerate(visible_items[:25]):
            self.add_item(InventoryItemButton(self.config, self.manager, item, row=idx // 5))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This inventory menu belongs to someone else.", ephemeral=True)
            return False
        return True


class InventoryItemButton(ui.Button):
    def __init__(self, config: dict, manager: TamagotchiManager, item: dict, row: int = 0):
        label = f"{item['name']} x{item['stock_text']}"
        if len(label) > 80:
            label = label[:77] + "..."
        super().__init__(
            label=label,
            emoji=item.get("emoji"),
            style=inventory_button_style(item),
            row=row,
        )
        self.config = config
        self.manager = manager
        self.item_id = item["id"]

    async def callback(self, interaction: discord.Interaction):
        await _consume_inventory_item(interaction, self.config, self.manager, self.item_id)


class ChatterButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="Chatter",
            emoji="💬",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_chatter",
            row=0,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return

        remaining = self.manager.check_cooldown("chatter")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _discord_relative_time(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        self.manager.set_cooldown("chatter", int(self.config.get("tama_chatter_cooldown", 30)))
        await interaction.response.send_message("💬 Letting the bot jump into the conversation...", ephemeral=True)
        if interaction.channel is not None:
            await self.manager.run_chatter_prompt(interaction.channel)


class PlayButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="🎮 Play",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_play",
            row=0,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return

        remaining = self.manager.check_cooldown("play")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _discord_relative_time(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if not can_use_energy(self.config):
            await interaction.response.send_message(_no_energy_message(self.config), ephemeral=True)
            return

        await interaction.response.send_message(
            "🎮 Choose a game to play.",
            view=GameSelectView(self.config, self.manager, interaction.user.id),
            ephemeral=True,
        )


class MedicateButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="💉 Medicate",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_medicate",
            row=0,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return

        remaining = self.manager.check_cooldown("medicate")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _discord_relative_time(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        max_health = float(self.config.get("tama_health_max", 100))
        current_health = float(self.config.get("tama_health", 0))
        is_sick = self.config.get("tama_sick", False)
        dirt = int(self.config.get("tama_dirt", 0) or 0)
        threshold = float(self.config.get("tama_health_threshold", 20.0))
        low_hunger = float(self.config.get("tama_hunger", 0) or 0) < threshold
        low_thirst = float(self.config.get("tama_thirst", 0) or 0) < threshold

        if dirt > 0:
            await interaction.response.send_message(
                "🚿 Clean the bot before medicating it.",
                ephemeral=True,
            )
            return

        if is_sick and (low_hunger or low_thirst):
            needs = []
            if low_hunger:
                needs.append("hunger")
            if low_thirst:
                needs.append("thirst")
            needs_text = " and ".join(needs)
            await interaction.response.send_message(
                f"🍔🥤 {needs_text.capitalize()} must be above {threshold:g} before you can medicate the bot.",
                ephemeral=True,
            )
            return

        if not is_sick and current_health >= max_health:
            msg = self.config.get("tama_resp_medicate_healthy", "I'm not sick!")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        heal_amount = max(0.0, float(self.config.get("tama_medicate_health_heal", 20.0)))
        happiness_cost = max(0.0, float(self.config.get("tama_medicate_happiness_cost", 3.0)))
        self.config["tama_sick"] = False
        self.config["tama_health"] = min(max_health, round(current_health + heal_amount, 2))
        self.config["tama_happiness"] = max(
            0.0,
            round(float(self.config.get("tama_happiness", 0)) - happiness_cost, 2),
        )
        save_config(self.config)
        self.manager.set_cooldown("medicate", self.config.get("tama_cd_medicate", 60))
        msg = self.config.get("tama_resp_medicate", "💊 Feeling better!")
        msg = _public_action_message(
            interaction,
            msg,
            action_summary="gave **{bot_name}** medicine",
        )
        await interaction.response.send_message(
            append_tamagotchi_footer(msg, self.config, self.manager),
            view=TamagotchiView(self.config, self.manager),
        )


class CleanButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="🚿 Clean",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_clean",
            row=0,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return

        remaining = self.manager.check_cooldown("clean")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _discord_relative_time(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if self.config.get("tama_dirt", 0) <= 0:
            msg = self.config.get("tama_resp_clean_none", "Already clean!")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        self.config["tama_dirt"] = 0
        self.config["tama_dirt_grace_until"] = 0.0
        save_config(self.config)
        self.manager._clear_dirt_grace(save=False)
        self.manager.set_cooldown("clean", self.config.get("tama_cd_clean", 60))
        msg = self.config.get("tama_resp_clean", "🚿 Squeaky clean!")
        msg = _public_action_message(
            interaction,
            msg,
            action_summary="gave **{bot_name}** a shower",
        )
        await interaction.response.send_message(
            append_tamagotchi_footer(msg, self.config, self.manager),
            view=TamagotchiView(self.config, self.manager),
        )


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Rock-Paper-Scissors Minigame
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

_RPS_EMOJI = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}


class GameSelectView(ui.View):
    def __init__(self, config: dict, manager: TamagotchiManager, owner_id: int):
        super().__init__(timeout=300)
        self.config = config
        self.manager = manager
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This game menu belongs to someone else.", ephemeral=True)
            return False
        return True

    @ui.button(label="RPS", emoji="✂️", style=discord.ButtonStyle.primary, row=0)
    async def rps_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return
        if not can_use_energy(self.config):
            await interaction.response.send_message(_no_energy_message(self.config), ephemeral=True)
            return
        remaining = self.manager.check_cooldown("play")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _discord_relative_time(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        happy_gain = float(self.config.get("tama_play_happiness", 0.0) or 0.0)
        if happy_gain:
            apply_direct_happiness_delta(self.config, happy_gain)

        deplete_energy_game(self.config)
        started_sleep = False
        if should_auto_sleep(self.config):
            self.manager.begin_rest(interaction.channel_id)
            started_sleep = True
        self.manager.set_cooldown("play", self.config.get("tama_cd_play", 60))

        bot_choice = random.choice(["rock", "paper", "scissors"])
        msg = self.config.get("tama_resp_play", "🎮 Let's play!")
        rps_view = RPSView(self.config, self.manager, bot_choice)
        await interaction.response.edit_message(
            content=f"{msg}\n**Rock, Paper, Scissors — pick your move!**",
            view=rps_view,
        )
        if started_sleep:
            await self.manager.send_sleep_announcement(interaction.channel_id)

    @ui.button(label="Lucky Gift", emoji="🎁", style=discord.ButtonStyle.success, row=0)
    async def lucky_gift_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return
        if not can_use_energy(self.config):
            await interaction.response.send_message(_no_energy_message(self.config), ephemeral=True)
            return
        remaining = self.manager.check_cooldown("lucky_gift")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _discord_relative_time(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        pool = _lucky_gift_pool(self.config)
        if not pool:
            await interaction.response.send_message("🎁 The lucky gift pool is empty right now.", ephemeral=True)
            return

        deplete_energy_game(self.config)
        started_sleep = False
        if should_auto_sleep(self.config):
            self.manager.begin_rest(interaction.channel_id)
            started_sleep = True
        self.manager.set_cooldown("lucky_gift", self.config.get("tama_cd_lucky_gift", 600))

        if interaction.channel is None:
            await interaction.response.send_message("🎁 I couldn't find a channel to open the gift in.", ephemeral=True)
            return

        duration = max(1, int(self.config.get("tama_lucky_gift_duration", 30)))
        giver_name = interaction.user.display_name
        bot_name = _bot_display_name(interaction)
        await interaction.response.defer()
        countdown_message = await interaction.channel.send(
            _lucky_gift_countdown_text(self.config, giver_name, bot_name, duration)
        )

        for seconds_left in range(duration - 1, 0, -1):
            await asyncio.sleep(1)
            try:
                await countdown_message.edit(
                    content=_lucky_gift_countdown_text(self.config, giver_name, bot_name, seconds_left),
                )
            except Exception:
                break

        prize = random.choice(pool)
        happiness_delta, energy_delta, _, stored_in_inventory = _apply_lucky_gift_reward(self.config, prize)
        reveal = _lucky_gift_reveal_text(
            giver_name,
            bot_name,
            prize,
            happiness_delta,
            energy_delta,
            stored_in_inventory,
        )
        try:
            await countdown_message.edit(
                content=append_tamagotchi_footer(reveal, self.config, self.manager),
                view=TamagotchiView(self.config, self.manager),
            )
        except Exception:
            countdown_message = await interaction.channel.send(
                append_tamagotchi_footer(reveal, self.config, self.manager),
                view=TamagotchiView(self.config, self.manager),
            )
        _log_tamagotchi_action(
            self.config,
            interaction,
            "lucky_gift",
            countdown_message.id,
            item_id=prize["id"],
            item_name=prize["name"],
            item_emoji=prize["emoji"],
        )
        if started_sleep:
            await self.manager.send_sleep_announcement(interaction.channel_id)


class RPSView(ui.View):
    def __init__(self, config: dict, manager: TamagotchiManager, bot_choice: str):
        super().__init__(timeout=300)
        self.config = config
        self.manager = manager
        self.bot_choice = bot_choice

    async def _finish_round(self, interaction: discord.Interaction, user_choice: str) -> None:
        user_name = interaction.user.display_name
        bot_name = _bot_display_name(interaction)
        user_emoji = _RPS_EMOJI.get(user_choice, "🎮")
        bot_emoji = _RPS_EMOJI.get(self.bot_choice, "🎮")

        outcome_key = resolve_rps_outcome(user_choice, self.bot_choice)
        if outcome_key == "draw":
            outcome = "It's a draw."
        elif outcome_key == "user_win":
            outcome = f"**{user_name}** wins."
        else:
            outcome = f"**{bot_name}** wins."

        happiness_delta = apply_rps_happiness_reward(self.config, outcome_key)
        if happiness_delta:
            save_config(self.config)

        public_result = (
            "🎮 **Rock, Paper, Scissors**\n"
            f"**{user_name}** chose {user_emoji} **{user_choice.title()}**.\n"
            f"**{bot_name}** chose {bot_emoji} **{self.bot_choice.title()}**.\n"
            f"{outcome}"
        )
        if happiness_delta > 0:
            public_result += f"\n😊 Happiness +{_fs(happiness_delta)}."
        elif happiness_delta < 0:
            public_result += f"\n☹️ Happiness {_fs(happiness_delta)}."

        await interaction.response.edit_message(
            content=f"You picked {user_emoji} **{user_choice.title()}**. Result posted publicly.",
            view=None,
        )

        if interaction.channel is None:
            return

        result_message = await interaction.channel.send(
            append_tamagotchi_footer(public_result, self.config, self.manager),
            view=TamagotchiView(self.config, self.manager),
        )
        _log_tamagotchi_action(
            self.config,
            interaction,
            "play",
            result_message.id,
        )

    @ui.button(label="Rock", emoji="🪨", style=discord.ButtonStyle.secondary, row=0)
    async def rock_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._finish_round(interaction, "rock")

    @ui.button(label="Paper", emoji="📄", style=discord.ButtonStyle.secondary, row=0)
    async def paper_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._finish_round(interaction, "paper")

    @ui.button(label="Scissors", emoji="✂️", style=discord.ButtonStyle.secondary, row=0)
    async def scissors_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._finish_round(interaction, "scissors")

