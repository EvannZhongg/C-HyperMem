from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c_hypermem import Memory
from c_hypermem.errors import IngestionNotConfiguredError


def main() -> None:
    memory = Memory.from_config(
        {
            "storage": {"path": str(Path("runs") / "quickstart.sqlite3")},
        }
    )
    namespace = "quickstart"
    memory.reset(namespace)
    try:
        memory.add_memory(
            user_input="Alice prefers morning interviews.",
            assistant_output="I will remember that.",
            namespace=namespace,
            metadata={"session_id": "S1", "date": "2024-01-03"},
        )
    except IngestionNotConfiguredError as exc:
        print(exc)
    print(memory.stats(namespace))
    memory.close()


if __name__ == "__main__":
    main()
