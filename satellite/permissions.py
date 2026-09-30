"""Server authority. No PC dispatcher or tool handlers are reachable here."""
from types import MappingProxyType

CAPABILITIES = MappingProxyType({
    'conversation': True, 'device_memory': True, 'browser_voice': True,
    'research': False, 'run_terminal': False, 'open_app': False,
    'create_file': False, 'read_file': False, 'edit_file': False,
    'kali_tool': False, 'connect_device': False, 'render_3d': False,
    'list_skills': False, 'control_pc': False,
})
BLOCKED = 'This action is not available from Satellite Beta. PC control and tools are disabled; you can still chat.'


def conversation_reply(result):
    """Fail closed for every action, including future/unknown or malformed ones."""
    if not isinstance(result, dict):
        raise ValueError('Invalid provider response')
    action = result.get('action')
    if not isinstance(action, dict) or action.get('tool') != 'none' or not isinstance(action.get('args', {}), dict):
        return BLOCKED
    speech = result.get('speak')
    if not isinstance(speech, str) or not speech.strip():
        raise ValueError('Empty provider response')
    return speech
