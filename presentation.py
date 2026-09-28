"""Human-readable tool results shared by the terminal and browser."""
import json
from privacy import redact


def readable_output(output: str) -> str:
    output = redact(output)
    try:
        data = json.loads(output)
    except (ValueError, TypeError):
        return output
    def render(value, indent=0):
        if isinstance(value, dict):
            lines = []
            for key, item in value.items():
                label = str(key).replace('_', ' ').capitalize()
                if item == '' or item is None:
                    continue
                if isinstance(item, (dict, list)):
                    lines.append(' ' * indent + label + ':\n' + render(item, indent + 2))
                else:
                    lines.append(' ' * indent + label + ': ' + str(item))
            return '\n\n'.join(lines)
        if isinstance(value, list):
            return '\n'.join(' ' * indent + '• ' + render(item, indent).lstrip() for item in value)
        return str(value)
    return render(data)
