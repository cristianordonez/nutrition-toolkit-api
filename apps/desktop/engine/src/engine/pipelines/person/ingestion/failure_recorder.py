"""Count the failures an ingestion run reported, so a caller can show them.

Extraction is deliberately fault-tolerant: one unreadable page, or one note
the model refuses, must not lose the rest of a fifty-page report. Each
extractor therefore isolates its own failures, logs them, and carries on.

That is the right behaviour and the wrong report. A run where eighteen of
thirty-six pages failed returns facts and looks like a success -- the only
record of the loss is in the log file, which nobody reads after a run that
appeared to work.

This watches the logging stream for the duration of one run and counts what
was reported as an error. Capturing log records rather than threading a
result type through every extractor is a deliberate trade: it needs no change
to the extractor contract and it catches failure paths that predate it or are
added later. The coupling it accepts is that a failure must be logged at
ERROR to be counted -- which is what the code already does, and what anyone
diagnosing a run would grep for anyway.
"""

from __future__ import annotations

import logging
import typing

if typing.TYPE_CHECKING:
    import types

#: How many distinct messages to keep. Enough to show what went wrong without
#: turning a UI notice into a log viewer; the file has the rest.
_MAX_SAMPLES = 3


class IngestionFailureRecorder(logging.Handler):
    """Collect error records emitted while one ingestion run is in progress."""

    def __init__(self) -> None:
        """Start with no failures recorded."""
        super().__init__(level=logging.ERROR)
        self.count = 0
        self._samples: list[str] = []
        self._distinct: set[str] = set()

    @property
    def samples(self) -> list[str]:
        """A few distinct failure messages, for showing the reader."""
        return list(self._samples)

    @property
    def unshown_messages(self) -> int:
        """How many distinct messages `samples` left out.

        Three samples describe a run where everything failed the same way.
        They mislead on a run where several things went wrong at once: the
        reader sees a quota error and assumes that is the whole story, when
        two other causes went unmentioned. This is what makes the omission
        visible, so they know to open the log.
        """
        return max(len(self._distinct) - len(self._samples), 0)

    def emit(self, record: logging.LogRecord) -> None:
        """Record one failure.

        Never raises: a problem while counting failures must not become a
        second failure on top of the one being counted.
        """
        self.count += 1
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a bad format string is not our problem
            return
        self._distinct.add(message)
        if len(self._samples) < _MAX_SAMPLES and message not in self._samples:
            self._samples.append(message)

    def __enter__(self) -> typing.Self:
        """Attach to the root logger, where every module's records arrive."""
        logging.getLogger().addHandler(self)
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: types.TracebackType | None,
    ) -> typing.Literal[False]:
        """Detach, so a later run does not inherit this run's count."""
        logging.getLogger().removeHandler(self)
        return False


__all__ = ["IngestionFailureRecorder"]
