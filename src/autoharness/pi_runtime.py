"""Explicit Pi configuration policy; no generic aliases escape to child processes."""
PREFIX = "AUTOHARNESS_PI_"


def external_environment(environ):
    return {key: value for key, value in environ.items()
            if not key.startswith("AUTOHARNESS_") or key.startswith(PREFIX)}


def apply_config(config):
    """Called once by the Pi CLI, after importing the core with a clean environment."""
    import os

    integer_settings = {
        "REFLECT_EVERY_N": 1, "CONSOLIDATE_EVERY_N": None, "DIGEST_EXCHANGES": 1,
        "SKILL_BODY_MAX_LINES": 1, "SKILL_DESC_MAX_CHARS": None, "INDEX_DESC_MAX_CHARS": 4,
        "SNAPSHOT_KEEP": 0, "NOTIFY_TIMEOUT_S": 1,
    }
    for name, minimum in integer_settings.items():
        setattr(config, name, config._int_env(PREFIX + name, getattr(config, name), minimum=minimum))
    for name in ("INDEX_SUSPENDED", "DISABLE_GLOBAL", "GRADUATION_SUSPENDED"):
        attribute = "GRADUATION_REVIEW_SUSPENDED" if name == "GRADUATION_SUSPENDED" else name
        setattr(config, attribute, config._bool_env(PREFIX + name, getattr(config, attribute)))
    for attribute, suffix in (("MATURITY_THRESHOLD", "MATURITY"), ("CAPACITY", "CAPACITY")):
        current = getattr(config, attribute)
        setattr(config, attribute, {level: config._int_env(f"{PREFIX}{suffix}_{level.upper()}", value, minimum=0)
                                    for level, value in current.items()})
    config.NOTIFY = os.environ.get(PREFIX + "NOTIFY", "").strip().lower()
    config.NOTIFY_CMD = os.environ.get(PREFIX + "NOTIFY_CMD", "")
    config.REFLECTOR_CARRIER = "bundle"
    config.CHILD_SESSION_ENV = PREFIX + "CHILD_SESSION"
    config.RUN_ID_ENV = PREFIX + "RUN_ID"
    config.PROJECT_ROOT_ENV = PREFIX + "PROJECT_ROOT"
    config.NOTIFY_SUMMARY_ENV = PREFIX + "NOTIFY_SUMMARY"
