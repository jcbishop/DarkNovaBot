from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import random
from typing import Optional, Protocol


class RandomSource(Protocol):
    def randint(self, start: int, end: int) -> int:
        ...


class RollType(str, Enum):
    ATTACK = "attack"
    NON_ATTACK = "non_attack"


class Outcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CRITICAL_SUCCESS = "critical_success"
    CRITICAL_HIT = "critical_hit"
    DRAMATIC_FAILURE = "dramatic_failure"


@dataclass(frozen=True)
class ResolutionRequest:
    stat_1: int
    stat_2: int
    target_number: int
    modifier: int = 0
    advantage: int = 0
    disadvantage: int = 0
    roll_type: RollType = RollType.NON_ATTACK
    critical_modifier: int = 5
    natural_trigger: Optional[int] = None
    trigger_requires_success: bool = True


@dataclass(frozen=True)
class ResolutionResult:
    die_1: int
    die_2: int
    natural_roll: int
    high_die: int
    low_die: int

    original_advantage: int
    original_disadvantage: int
    net_advantage: int
    net_disadvantage: int

    bonus_dice: tuple[int, ...]
    advantage_modifier: int

    stat_1: int
    stat_2: int
    other_modifier: int
    final_result: int
    target_number: int
    margin: int

    success: bool
    doubles: bool
    outcome: Outcome

    natural_trigger: Optional[int]
    natural_condition_met: bool
    natural_effect_triggered: bool

    critical_modifier: int

    @property
    def effect_die(self) -> int:
        """Dark Nova uses HD unless an effect specifically calls for LD."""
        return self.high_die


def cancel_stacks(
    advantage: int,
    disadvantage: int,
) -> tuple[int, int]:
    """
    Cancel Advantage and Disadvantage stacks on a 1:1 basis.

    Stacks cannot be negative. Any stacks remaining after cancellation are
    retained, although no more than five d6s are rolled.
    """
    advantage = max(0, advantage)
    disadvantage = max(0, disadvantage)

    cancelled = min(advantage, disadvantage)

    return (
        advantage - cancelled,
        disadvantage - cancelled,
    )


def calculate_stack_modifier(dice: tuple[int, ...]) -> int:
    """
    Determine the magnitude of Advantage or Disadvantage.

    No sixes:
        Use the highest d6.

    One six:
        The value is 6.

    Additional sixes:
        Add +2 for each six after the first.
    """
    if not dice:
        return 0

    sixes = dice.count(6)

    if sixes == 0:
        return max(dice)

    return 6 + (2 * (sixes - 1))


def determine_outcome(
    *,
    success: bool,
    doubles: bool,
    roll_type: RollType,
) -> Outcome:
    if doubles and success:
        if roll_type == RollType.ATTACK:
            return Outcome.CRITICAL_HIT

        return Outcome.CRITICAL_SUCCESS

    if doubles and not success:
        return Outcome.DRAMATIC_FAILURE

    if success:
        return Outcome.SUCCESS

    return Outcome.FAILURE


def resolve(
    request: ResolutionRequest,
    rng: RandomSource = random,
) -> ResolutionResult:
    if request.target_number < 0:
        raise ValueError("Target Number cannot be negative.")

    if request.advantage < 0:
        raise ValueError("Advantage stacks cannot be negative.")

    if request.disadvantage < 0:
        raise ValueError("Disadvantage stacks cannot be negative.")

    die_1 = rng.randint(1, 10)
    die_2 = rng.randint(1, 10)

    natural_roll = die_1 + die_2
    high_die = max(die_1, die_2)
    low_die = min(die_1, die_2)
    doubles = die_1 == die_2

    net_advantage, net_disadvantage = cancel_stacks(
        request.advantage,
        request.disadvantage,
    )

    if net_advantage > 0:
        number_of_d6s = min(net_advantage, 5)
        sign = 1
    elif net_disadvantage > 0:
        number_of_d6s = min(net_disadvantage, 5)
        sign = -1
    else:
        number_of_d6s = 0
        sign = 0

    bonus_dice = tuple(
        rng.randint(1, 6)
        for _ in range(number_of_d6s)
    )

    stack_magnitude = calculate_stack_modifier(bonus_dice)
    advantage_modifier = sign * stack_magnitude

    final_result = (
        natural_roll
        + request.stat_1
        + request.stat_2
        + request.modifier
        + advantage_modifier
    )

    # Equals or exceeds TN, so ties favor the roller/player.
    success = final_result >= request.target_number
    margin = final_result - request.target_number

    outcome = determine_outcome(
        success=success,
        doubles=doubles,
        roll_type=request.roll_type,
    )

    natural_condition_met = (
        request.natural_trigger is not None
        and natural_roll >= request.natural_trigger
    )

    natural_effect_triggered = (
        natural_condition_met
        and (
            success
            or not request.trigger_requires_success
        )
    )

    return ResolutionResult(
        die_1=die_1,
        die_2=die_2,
        natural_roll=natural_roll,
        high_die=high_die,
        low_die=low_die,
        original_advantage=request.advantage,
        original_disadvantage=request.disadvantage,
        net_advantage=net_advantage,
        net_disadvantage=net_disadvantage,
        bonus_dice=bonus_dice,
        advantage_modifier=advantage_modifier,
        stat_1=request.stat_1,
        stat_2=request.stat_2,
        other_modifier=request.modifier,
        final_result=final_result,
        target_number=request.target_number,
        margin=margin,
        success=success,
        doubles=doubles,
        outcome=outcome,
        natural_trigger=request.natural_trigger,
        natural_condition_met=natural_condition_met,
        natural_effect_triggered=natural_effect_triggered,
        critical_modifier=request.critical_modifier,
    )