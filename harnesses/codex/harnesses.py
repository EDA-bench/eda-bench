from harnesses.codex.utils import build_prompt, make_harness, run  # noqa: F401
from harnesses.utils import register_builtin_harnesses

MODELS = ("gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex-spark")
ACCESS_MODES = ("web", "no_web")
LEVELS = ("low", "medium", "high", "xhigh")

SUPPORTED_CONFIGS = tuple(
    (model, access, level)
    for model in MODELS
    for access in ACCESS_MODES
    for level in LEVELS
)

register_builtin_harnesses(
    globals(),
    configs=SUPPORTED_CONFIGS,
    make_harness=make_harness,
)
