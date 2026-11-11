import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_permission_file_matches_the_owners_explicit_allow_list():
    data = json.loads((ROOT/'.claude/settings.json').read_text(encoding='utf-8'))
    assert data == {'permissions': {'allow': ['Bash', 'Read', 'Edit', 'Write', 'Glob', 'Grep', 'ToolSearch', 'Artifact',
        'mcp__Gmail__search_threads', 'mcp__Gmail__get_message', 'mcp__Gmail__send_message',
        'mcp__Claude_Code_Remote__get_session', 'mcp__claude-code-remote__get_session']}}


def test_five_source_prompts_stand_down_only_on_a_real_takeover():
    expected = {'ROUTINE_PROMPT.md': 1, 'ROUTINE_FALLBACKS.md': 2, 'ROUTINE_NOON.md': 1, 'ROUTINE_EVENING.md': 1}
    for name, count in expected.items():
        text = (ROOT/name).read_text(encoding='utf-8')
        assert text.count('RESCUE STAND-DOWN:') == count
        assert text.count('A subject beginning `RB Morning Rescue TEST` is only a test') == count
