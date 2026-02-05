"""Constants for Karakeep synchronization."""

TAG_BSR_READ = "bsr-read"
TAG_BSR_SYNCED = "bsr-synced"

# Legacy hash length for backward compatibility
LEGACY_HASH_LENGTH = 16

BOOKMARK_PAGE_SIZE = 100

# Retry defaults for sync operations (separate from HTTP client retries)
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_SECONDS = 0.5
DEFAULT_MAX_DELAY_SECONDS = 5.0
DEFAULT_BACKOFF_FACTOR = 2.0
