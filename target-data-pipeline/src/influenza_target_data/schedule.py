"""GitHub Actions time-window gate in Europe/Stockholm."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from .weeks import STOCKHOLM, previous_week


def schedule_state(now: datetime | None = None) -> dict[str, str]:
    if now is None:
        now = datetime.now(timezone.utc)
    local = now.astimezone(STOCKHOLM)
    should_poll = local.weekday() in {3, 4, 5} and 8 <= local.hour <= 18
    is_final = local.weekday() == 5 and local.hour == 18
    return {
        "should_poll": str(should_poll).lower(),
        "is_final": str(is_final).lower(),
        "target_week": previous_week(now),
        "local_time": local.isoformat(),
    }


def main() -> None:
    state = schedule_state()
    for key, value in state.items():
        print(f"{key}={value}")
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            for key, value in state.items():
                handle.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
