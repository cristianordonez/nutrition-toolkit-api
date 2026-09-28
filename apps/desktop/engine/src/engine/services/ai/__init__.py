"""AI providers and the controller that chooses between them.

``controller.AIController`` selects ``local_provider.LocalAIProvider``
(llama.cpp on this machine) or ``openai_provider.OpenAIProvider`` from the
user's setting. ``boundary`` turns either provider's transport failures into
the ``errors`` hierarchy. See ``docs/local-ai.md``.
"""

from __future__ import annotations
