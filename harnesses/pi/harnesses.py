from harnesses.pi.utils import build_prompt, make_harness, run  # noqa: F401
from harnesses.utils import register_builtin_harnesses

SUPPORTED_CONFIGS = (
    ("gemini-3.1-pro-preview", "web", "high"),
    ("deepseek/deepseek-v4-pro", "web", "high"),
)

register_builtin_harnesses(
    globals(),
    configs=SUPPORTED_CONFIGS,
    make_harness=make_harness,
)
