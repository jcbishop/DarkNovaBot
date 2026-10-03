from __future__ import annotations

import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from resolution import (
    Outcome,
    ResolutionRequest,
    ResolutionResult,
    RollType,
    resolve,
)


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

TOKEN = os.getenv("DISCORD_TOKEN")
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")


def signed(value: int) -> str:
    return f"{value:+d}"


def format_bonus_dice(result: ResolutionResult) -> str:
    if not result.bonus_dice:
        return "None"

    dice = ", ".join(str(die) for die in result.bonus_dice)

    if result.net_advantage:
        kind = "Advantage"
    else:
        kind = "Disadvantage"

    sixes = result.bonus_dice.count(6)

    if sixes > 1:
        explanation = (
            f"{sixes} sixes: 6 + "
            f"{sixes - 1} × 2 = "
            f"{abs(result.advantage_modifier)}"
        )
    else:
        explanation = (
            f"Applied modifier: {signed(result.advantage_modifier)}"
        )

    return f"{kind}: [{dice}]\n{explanation}"


def outcome_title(outcome: Outcome) -> str:
    titles = {
        Outcome.SUCCESS: "Success",
        Outcome.FAILURE: "Failure",
        Outcome.CRITICAL_SUCCESS: "Critical Success",
        Outcome.CRITICAL_HIT: "Critical Hit",
        Outcome.DRAMATIC_FAILURE: "Dramatic Failure",
    }

    return titles[outcome]


def outcome_color(outcome: Outcome) -> discord.Color:
    colors = {
        Outcome.SUCCESS: discord.Color.dark_green(),
        Outcome.FAILURE: discord.Color.red(),
        Outcome.CRITICAL_SUCCESS: discord.Color.brand_green(),
        Outcome.CRITICAL_HIT: discord.Color.orange(),
        Outcome.DRAMATIC_FAILURE: discord.Color.dark_red(),
    }

    return colors[outcome]


def outcome_details(result: ResolutionResult) -> str:
    if result.outcome == Outcome.CRITICAL_SUCCESS:
        return (
            "**Choose one:**\n"
            "• **Surge:** Gain 1 Advantage on your next related roll.\n"
            "• **Momentum:** Reduce the Action cost of your next "
            "Action by 1, minimum 0.\n"
            "• **Insight:** Ask one additional relevant question.\n"
            "• **Precision:** Add HD to the result when determining "
            "degree of success.\n"
            "• **Efficiency:** Reduce the required time by one step."
        )

    if result.outcome == Outcome.CRITICAL_HIT:
        return (
            f"• Add **+{result.critical_modifier}** to damage.\n"
            "• Ignore the target's remaining Guard.\n"
            "• Deal damage directly to Vigor."
        )

    if result.outcome == Outcome.DRAMATIC_FAILURE:
        return (
            "• The GM introduces a significant complication.\n"
            "• Gain **2 XP**."
        )

    if result.outcome == Outcome.SUCCESS:
        return "The action equals or exceeds the Target Number."

    return (
        "The action did not meet or exceed the Target Number.\n"
        "Once per session, the player may request a Voluntary "
        "Dramatic Failure for 4 XP, subject to GM approval."
    )


def build_result_embed(
    interaction: discord.Interaction,
    result: ResolutionResult,
) -> discord.Embed:
    title = f"Dark Nova: {outcome_title(result.outcome)}"

    embed = discord.Embed(
        title=title,
        color=outcome_color(result.outcome),
    )

    embed.set_author(
        name=interaction.user.display_name,
        icon_url=interaction.user.display_avatar.url,
    )

    core_math = (
        f"2d10 `{result.die_1} + {result.die_2}`\n"
        f"Stats `{signed(result.stat_1)} "
        f"{signed(result.stat_2)}`\n"
        f"Modifier `{signed(result.other_modifier)}`\n"
        f"Adv./Disadv. `{signed(result.advantage_modifier)}`\n"
        f"**Total: {result.final_result} vs TN "
        f"{result.target_number}**"
    )

    embed.add_field(
        name="Core Roll",
        value=core_math,
        inline=False,
    )

    if result.margin >= 0:
        margin_text = f"Succeeded by **{result.margin}**"
    else:
        margin_text = f"Failed by **{abs(result.margin)}**"

    embed.add_field(
        name="Result",
        value=margin_text,
        inline=True,
    )

    embed.add_field(
        name="Effect Dice",
        value=(
            f"HD: **{result.high_die}**\n"
            f"LD: **{result.low_die}**"
        ),
        inline=True,
    )

    embed.add_field(
        name="Natural Roll",
        value=f"**{result.natural_roll}**",
        inline=True,
    )

    if (
        result.original_advantage > 0
        or result.original_disadvantage > 0
    ):
        cancellation_text = (
            f"Starting stacks: "
            f"{result.original_advantage} Advantage, "
            f"{result.original_disadvantage} Disadvantage\n"
            f"After cancellation: "
            f"{result.net_advantage} Advantage, "
            f"{result.net_disadvantage} Disadvantage\n"
            f"{format_bonus_dice(result)}"
        )

        embed.add_field(
            name="Advantage and Disadvantage",
            value=cancellation_text,
            inline=False,
        )

    if result.natural_trigger is not None:
        if result.natural_effect_triggered:
            trigger_text = (
                f"Triggered: Natural Roll "
                f"{result.natural_roll} ≥ "
                f"{result.natural_trigger}"
            )
        elif result.natural_condition_met:
            trigger_text = (
                f"Condition met, but the effect did not trigger "
                f"because the roll failed."
            )
        else:
            trigger_text = (
                f"Not triggered: Natural Roll "
                f"{result.natural_roll} < "
                f"{result.natural_trigger}"
            )

        embed.add_field(
            name="Natural Trigger",
            value=trigger_text,
            inline=False,
        )

    embed.add_field(
        name=outcome_title(result.outcome),
        value=outcome_details(result),
        inline=False,
    )

    if result.doubles:
        embed.set_footer(
            text=f"Doubles rolled: {result.die_1}, {result.die_2}"
        )
    else:
        embed.set_footer(
            text="Dark Nova unified resolution"
        )

    return embed


class DarkNovaBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

    async def setup_hook(self) -> None:
        if TEST_GUILD_ID:
            guild = discord.Object(id=int(TEST_GUILD_ID))

            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)

            logging.info(
                "Synced %s command(s) to test guild %s.",
                len(synced),
                TEST_GUILD_ID,
            )
        else:
            synced = await self.tree.sync()

            logging.info(
                "Synced %s global command(s).",
                len(synced),
            )


bot = DarkNovaBot()


@bot.event
async def on_ready() -> None:
    if bot.user is not None:
        logging.info(
            "Logged in as %s (%s).",
            bot.user,
            bot.user.id,
        )


@bot.tree.command(
    name="resolve",
    description="Make a Dark Nova core resolution roll.",
)
@app_commands.describe(
    stat_1="First Stat added to the roll",
    stat_2="Second Stat added to the roll",
    target_number="Target Number the final result must meet",
    modifier="Other positive or negative modifiers",
    advantage="Number of Advantage stacks before cancellation",
    disadvantage="Number of Disadvantage stacks before cancellation",
    attack="Whether this is an attack roll",
    critical_modifier="Attack Critical Modifier, normally 5",
    natural_trigger="Optional Natural Roll threshold, such as 15",
    trigger_on_failure=(
        "Whether the Natural effect can trigger when the roll fails"
    ),
    private="Show the result only to you",
)
async def resolve_command(
    interaction: discord.Interaction,
    stat_1: app_commands.Range[int, -50, 50],
    stat_2: app_commands.Range[int, -50, 50],
    target_number: app_commands.Range[int, 0, 200],
    modifier: app_commands.Range[int, -100, 100] = 0,
    advantage: app_commands.Range[int, 0, 100] = 0,
    disadvantage: app_commands.Range[int, 0, 100] = 0,
    attack: bool = False,
    critical_modifier: app_commands.Range[int, 0, 100] = 5,
    natural_trigger: app_commands.Range[int, 2, 20] | None = None,
    trigger_on_failure: bool = False,
    private: bool = False,
) -> None:
    request = ResolutionRequest(
        stat_1=stat_1,
        stat_2=stat_2,
        target_number=target_number,
        modifier=modifier,
        advantage=advantage,
        disadvantage=disadvantage,
        roll_type=(
            RollType.ATTACK
            if attack
            else RollType.NON_ATTACK
        ),
        critical_modifier=critical_modifier,
        natural_trigger=natural_trigger,
        trigger_requires_success=not trigger_on_failure,
    )

    result = resolve(request)
    embed = build_result_embed(interaction, result)

    await interaction.response.send_message(
        embed=embed,
        ephemeral=private,
    )


@resolve_command.error
async def resolve_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    logging.exception(
        "Resolve command failed.",
        exc_info=error,
    )

    message = (
        "I couldn't complete that Dark Nova roll. "
        "Check the values and try again."
    )

    if interaction.response.is_done():
        await interaction.followup.send(
            message,
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            message,
            ephemeral=True,
        )


if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing. Add it to your .env file."
    )


bot.run(TOKEN)