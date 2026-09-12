"""Day99 DESIGN bounds, not measured effects; protected constants.py is unchanged.

See PREREGISTER_day99_deepseek.md. No network, environment reads or state writes
at import. Trading thresholds reuse report.min_sided_p and dashboard's clamp.
"""

BASE_URL = 'https://api.deepseek.com'
DEFAULT_MODEL = 'deepseek-chat'
PROMPT_VERSION = 'day99-v1'
SCHEMA_VERSION = 1
MAX_CANDIDATES = 500
BATCH_SIZE = 25
REQUEST_TIMEOUT = 12.0
PREP_BUDGET_SECONDS = 120.0
PUBLIC_INPUT_BUDGET_SECONDS = 25.0
PUBLIC_REQUEST_TIMEOUT = 4.0
PUBLIC_BATCH_SIZE = 4
MAX_RESPONSE_CHARS = 200_000
MAX_COMPLETION_TOKENS = 8192
MAX_PROMPT_CHARS = 300_000
MAX_RATIONALE_CHARS = 280
MAX_TITLE_CHARS = 400
MAX_NEWS_PER_CANDIDATE = 8
MAX_TAGS_PER_CANDIDATE = 8
MAX_NEWS_AGE_HOURS = 72
MAX_SNAPSHOT_AGE_HOURS = 6
MAX_INPUT_BYTES = 10_000_000
MACRO_KEYS = ('wti', 'cadusd', 'tsx', 'vix')
QUANT_WEIGHT = 0.8
SENTIMENT_WEIGHT = 0.2
SENTIMENT_PROBABILITY_SPAN = 0.15
MAX_PER_SIDE = 2
MIN_FORWARD_SESSIONS = 120
BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_BLOCK_SESSIONS = 5
BOOTSTRAP_SEED = 99
MDE_CRITICAL_SUM = 3.5 + 0.8416212336

DESIGN_PROVENANCE = {
    'registration': 'PREREGISTER_day99_deepseek.md',
    'kind': 'DESIGN',
    'accuracy_gain': None,
    'mde': None,
    'adopted': False,
    'note': 'Bounds and weights are specified design choices, not empirical alpha.',
}
