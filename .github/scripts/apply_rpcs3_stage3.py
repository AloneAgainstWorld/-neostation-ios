from __future__ import annotations

import base64
import re
import subprocess
import zlib
from pathlib import Path


SCRIPT_PATH = Path('.github/scripts/apply_rpcs3_stage3.py')


def _load_previous_wrapper() -> str:
    commits = subprocess.check_output(
        ['git', 'log', '--format=%H', '--', str(SCRIPT_PATH)],
        text=True,
    ).splitlines()
    for commit in commits[1:]:
        try:
            candidate = subprocess.check_output(
                ['git', 'show', f'{commit}:{SCRIPT_PATH}'],
                text=True,
            )
        except subprocess.CalledProcessError:
            continue
        if "b64decode('" in candidate:
            return candidate
    raise SystemExit('Could not locate the original compressed RPCS3 patch in Git history')


wrapper = _load_previous_wrapper()
match = re.search(r"b64decode\('([^']+)'\)", wrapper)
if not match:
    raise SystemExit('Compressed RPCS3 patch payload not found')

source = zlib.decompress(base64.b64decode(match.group(1))).decode('utf-8')

old_manual_marker = (
    '"          gameName: isMeloNxVirtual ? gameName : null,\\n",'
)
new_manual_marker = (
    '"          gameName: (systemFolder == \'android\' || isMeloNxVirtual)\\n'
    '              ? gameName\\n'
    '              : null,\\n",'
)
if source.count(old_manual_marker) != 1:
    raise SystemExit(
        f'Expected exactly one old manual marker, found {source.count(old_manual_marker)}'
    )
source = source.replace(old_manual_marker, new_manual_marker, 1)

old_generated_marker = (
    '"          gameName: (isMeloNxVirtual || isRpcs3Virtual) ? gameName : null,\\n"'
)
new_generated_marker = (
    '"          gameName:\\n'
    '              (systemFolder == \'android\' ||\\n'
    '                  isMeloNxVirtual ||\\n'
    '                  isRpcs3Virtual)\\n'
    '              ? gameName\\n'
    '              : null,\\n"'
)
if source.count(old_generated_marker) != 1:
    raise SystemExit(
        'Expected exactly one generated manual marker, '
        f'found {source.count(old_generated_marker)}'
    )
source = source.replace(old_generated_marker, new_generated_marker, 1)

exec(compile(source, '<rpcs3-stage3>', 'exec'))
