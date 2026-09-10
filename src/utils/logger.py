"""
DEPRECATED: Use src.api.lib.logger instead.

This module is kept for backward compatibility but will be removed in a future version.
Please migrate to the new structured logging:
    from src.api.lib.logger import auto_logger
    logger = auto_logger()
"""

import warnings

from src.api.lib.logger import auto_logger

warnings.warn(
    "src.utils.logger is deprecated. Use src.api.lib.logger instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Provide backward compatibility
logger = auto_logger()
