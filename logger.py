import logging
import sys
from config import LOG_LEVEL

logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, LOG_LEVEL.upper()))

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(getattr(logging, LOG_LEVEL.upper()))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
