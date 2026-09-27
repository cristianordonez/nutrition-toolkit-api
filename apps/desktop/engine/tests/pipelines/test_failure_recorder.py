"""Counting the failures an ingestion run hid behind its results."""

from __future__ import annotations

import logging

from engine.pipelines.person.ingestion.failure_recorder import (
    IngestionFailureRecorder,
)

logger = logging.getLogger("engine.test.failures")

#: Mirrors _MAX_SAMPLES in the recorder.
_MAX_SAMPLES = 3
_EXPECTED_FAILURES = 20


def test_errors_during_the_run_are_counted() -> None:
    with IngestionFailureRecorder() as failures:
        logger.error("Progress-note AI extraction failed on page 3")
        logger.error("Progress-note AI extraction failed on page 7")

    assert failures.count == 2  # noqa: PLR2004 - two logged errors
    assert "page 3" in failures.samples[0]


def test_a_clean_run_reports_nothing() -> None:
    """A successful run must not show a warning."""
    with IngestionFailureRecorder() as failures:
        logger.info("extraction completed: notes=36 failures=0")
        logger.warning("something worth noting but not a failure")

    assert failures.count == 0
    assert failures.samples == []


def test_samples_are_capped_and_deduplicated() -> None:
    """The notice shows a cause, not a log file."""
    with IngestionFailureRecorder() as failures:
        for _ in range(10):
            logger.error("You have no credits remaining")
        for page in range(10):
            logger.error("failed on page %s", page)

    assert failures.count == _EXPECTED_FAILURES
    assert len(failures.samples) <= _MAX_SAMPLES
    assert len(set(failures.samples)) == len(failures.samples)


def test_it_detaches_so_later_runs_start_clean() -> None:
    """A leaked handler would attribute one run's failures to the next."""
    with IngestionFailureRecorder() as first:
        logger.error("during the first run")

    logger.error("between runs")

    with IngestionFailureRecorder() as second:
        logger.error("during the second run")

    assert first.count == 1
    assert second.count == 1


def test_an_unformattable_message_is_still_counted() -> None:
    """Counting failures must not itself become a failure.

    Driven through ``emit`` rather than a log call: other handlers on the root
    logger format the same record, so a real call would raise in one of those
    before reaching this one. What is being pinned here is that this handler
    survives a record it cannot render and still counts it.
    """
    recorder = IngestionFailureRecorder()
    bad = logging.LogRecord(
        name="engine.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="missing arg %s %s",
        args=("only-one",),
        exc_info=None,
    )

    recorder.emit(bad)

    assert recorder.count == 1
    assert recorder.samples == []


#: More distinct causes than the recorder keeps samples of, so some are held
#: back however high that cap is set.
_CAUSES = ("quota", "unreadable page", "timeout", "bad schema", "io error")


def test_messages_beyond_the_samples_are_counted() -> None:
    """A reader shown a few causes must know when there were more.

    Otherwise a run that failed five different ways looks like a run that
    failed three, and the causes that went unmentioned are invisible.
    """
    recorder = IngestionFailureRecorder()
    with recorder:
        for cause in _CAUSES:
            logging.getLogger("engine.test").error(cause)

    assert len(recorder.samples) == _MAX_SAMPLES
    assert recorder.unshown_messages == len(_CAUSES) - _MAX_SAMPLES
    assert recorder.count == len(_CAUSES)


def test_one_cause_repeating_leaves_nothing_unshown() -> None:
    """The common case: everything failed the same way, so the samples are whole."""
    repeats = _MAX_SAMPLES * 10
    recorder = IngestionFailureRecorder()
    with recorder:
        for _ in range(repeats):
            logging.getLogger("engine.test").error("no credits remaining")

    assert recorder.unshown_messages == 0
    assert recorder.count == repeats


def test_an_unformattable_message_is_not_counted_as_unshown() -> None:
    """It was never rendered, so it cannot be reported as a message held back."""
    recorder = IngestionFailureRecorder()
    bad = logging.LogRecord(
        name="engine.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="missing arg %s %s",
        args=("only-one",),
        exc_info=None,
    )

    recorder.emit(bad)

    assert recorder.unshown_messages == 0
