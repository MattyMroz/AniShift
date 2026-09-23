"""Local episode selection awaiting one explicit subscription confirmation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from anishift.application import Subscription, SubscriptionOrder


@dataclass(slots=True)
class SubscriptionDraft:
    """Keep pending selection separate from persisted acquisition facts."""

    name: str
    numbers: tuple[Decimal, ...]
    selected: set[Decimal]
    future_from: Decimal | None
    tail: Decimal | None
    order: SubscriptionOrder | None = None
    subscription: Subscription | None = None
    completed: frozenset[Decimal] = frozenset()
    states: dict[Decimal, str] = field(default_factory=dict)
    cursor: int = 0

    @classmethod
    def from_order(cls, order: SubscriptionOrder, known: tuple[Decimal, ...]) -> SubscriptionDraft:
        """Prepare the chosen season and group without a persistence boundary."""
        count: int | None = order.context.episodes if order.context is not None else None
        numbers: tuple[Decimal, ...] = tuple(
            sorted(set(known) | {Decimal(number) for number in range(1, (count or 0) + 1)} | {order.first_episode})
        )
        tail: Decimal | None = None if count is not None else Decimal(int(max(numbers)) + 1)
        return cls(
            f"{order.series} [{order.group}]",
            numbers,
            {number for number in numbers if number >= order.first_episode},
            tail,
            tail,
            order=order,
        )

    @classmethod
    def from_subscription(
        cls, subscription: Subscription, work_states: Mapping[str, object] | None = None
    ) -> SubscriptionDraft:
        """Copy the saved range for editing without resetting completed episodes."""
        numbers: tuple[Decimal, ...] = tuple(
            sorted(
                {item.number for item in subscription.episodes}
                | {Decimal(number) for number in range(1, (subscription.season_episodes or 0) + 1)}
            )
        )
        states: dict[Decimal, str] = {item.number: item.state.value for item in subscription.episodes}
        states.update({Decimal(number): str(state) for number, state in (work_states or {}).items()})
        completed: frozenset[Decimal] = frozenset(number for number, state in states.items() if state == "completed")
        selected: set[Decimal] = {
            item.number for item in subscription.episodes if item.selected and item.number not in completed
        }
        tail: Decimal | None = (
            None
            if subscription.season_episodes is not None
            else subscription.future_from or Decimal(int(max(numbers, default=Decimal(0))) + 1)
        )
        return cls(
            f"{subscription.series} [{subscription.group}]",
            numbers,
            selected,
            subscription.future_from,
            tail,
            subscription=subscription,
            completed=completed,
            states=states,
        )

    def refresh_work_states(self, work_states: Mapping[str, object]) -> None:
        """Refresh owner facts without replacing the user's unconfirmed range edits."""
        states: dict[Decimal, str] = {Decimal(number): str(state) for number, state in work_states.items()}
        completed: frozenset[Decimal] = frozenset(number for number, state in states.items() if state == "completed")
        self.selected.difference_update(completed - self.completed)
        self.completed = completed
        self.states.update(states)

    def handle_key(self, key: str) -> None:
        """Edit only this draft; persistence requires the shell's explicit action."""
        count: int = len(self.numbers) + int(self.tail is not None)
        if key in {"up", "down"}:
            self.cursor = (self.cursor + (-1 if key == "up" else 1)) % max(count, 1)
        elif key in {"home", "end"}:
            self.cursor = 0 if key == "home" else max(count - 1, 0)
        elif key == "space" and self.cursor < len(self.numbers):
            self.selected ^= {self.numbers[self.cursor]}
        elif key == "space" and self.tail is not None:
            self.future_from = None if self.future_from is not None else self.tail
        elif key.casefold() == "text:a":
            self.selected.update(
                number for number in self.numbers if number == int(number) and number not in self.completed
            )

    def entries(self) -> list[tuple[str, bool | None]]:
        """Present episode numbers and facts without interpreting them as playback history."""
        labels: dict[str, str] = {
            "pending": "czeka na emisję",
            "due": "czeka na wydanie",
            "ordered": "przyjęto pobranie",
            "complete": "pobrano",
            "downloaded": "pobrano · czeka na przetwarzanie",
            "processing": "pobrano · przetwarzanie",
            "processing_failed": "pobrano · błąd przetwarzania",
            "completed": "ukończono produkty",
            "expired": "wymaga ponowienia",
            "missing": "brak wydania",
        }
        entries: list[tuple[str, bool | None]] = [
            (
                f"{number.normalize():f} · {labels.get(self.states.get(number, ''), 'do zamówienia')}",
                number in self.selected,
            )
            for number in self.numbers
        ]
        if self.tail is not None:
            entries.append(("Kolejne odcinki", self.future_from is not None))
        return entries
