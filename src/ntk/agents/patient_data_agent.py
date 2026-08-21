from __future__ import annotations

import typing

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent

logfire.configure()
logfire.instrument_system_metrics()
logfire.instrument_pydantic_ai()


class Sentiment(BaseModel):
    label: typing.Literal["positive", "negative", "neutral"]
    score: float = Field(ge=-1, le=1)


agent = Agent("test", output_type=Sentiment)


result = agent.run_sync(
    "How does pyodide let you run Python in the browser? (short answer please)",
)
