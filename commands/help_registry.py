from dataclasses import dataclass, field


@dataclass
class HelpEntry:
    """A single command listed in the help registry."""

    name: str  # e.g. "/tempvc setup <category>"
    description: str
    access: str  # "Everyone" | "Staff" | "Senior Staff"


@dataclass
class HelpGroup:
    """A named group of related commands."""

    name: str  # e.g. "tempvc"
    description: str
    commands: list[HelpEntry] = field(default_factory=list)


class HelpRegistry:
    """Registry of all help groups, populated at startup."""

    def __init__(self) -> None:
        self._groups: dict[str, HelpGroup] = {}

    def add_group(self, group: HelpGroup) -> None:
        """Add a help group to the registry."""
        self._groups[group.name] = group

    def groups(self) -> list[HelpGroup]:
        """Return all groups in insertion order."""
        return list(self._groups.values())

    def get_group(self, name: str) -> HelpGroup | None:
        """Return a group by name, or None if not found."""
        return self._groups.get(name)
