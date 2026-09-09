"""Protocol 2 evidence parser shared with the historical runner."""
import re


def evidence_ids(value):
    if not isinstance(value, list):
        raise ValueError('evidence must be a list')
    found, malformed = set(), []
    for item in value:
        if not isinstance(item, str):
            malformed.append(str(type(item)))
            continue
        matches = re.findall(r'D\s*(\d+)\s*:\s*(\d+)', item)
        found.update(f'D{int(s)}:{int(t)}' for s, t in matches)
        remainder = re.sub(r'D\s*\d+\s*:\s*\d+', '', item)
        if not matches or re.sub(r'[\s,;\[\]()]+', '', remainder):
            malformed.append(item)
    return found, malformed
