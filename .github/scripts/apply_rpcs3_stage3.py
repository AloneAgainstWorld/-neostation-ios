from __future__ import annotations

import base64
import re
import subprocess
import zlib
from pathlib import Path


SCRIPT_PATH = Path('.github/scripts/apply_rpcs3_stage3.py')
PAYLOAD_PATTERN = re.compile(r"b64decode\('([^']+)'\)")


def _load_previous_wrapper() -> str:
    # actions/checkout uses a depth-1 clone. Deepen the branch so this wrapper
    # can recover the original compressed generator from its previous commit.
    subprocess.run(
        ['git', 'fetch', '--deepen=50', 'origin', 'feature/rpcs3-stage3'],
        check=True,
    )
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
        match = PAYLOAD_PATTERN.search(candidate)
        if match and len(match.group(1)) > 1000:
            return match.group(1)
    raise SystemExit('Could not locate the original compressed RPCS3 patch in Git history')


def _print_failure_context(message: str, generator: str) -> None:
    label = message.removeprefix('Missing patch marker: ').strip()
    if not label:
        return
    index = generator.find(label)
    if index < 0:
        print(f'Could not find generator label for diagnostic: {label}')
        return
    print('\n--- RPCS3 generator context ---')
    print(generator[max(0, index - 3500): index + 3500])
    print('--- end generator context ---\n')


payload = _load_previous_wrapper()
source = zlib.decompress(base64.b64decode(payload)).decode('utf-8')

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

try:
    exec(compile(source, '<rpcs3-stage3>', 'exec'))
except SystemExit as exc:
    _print_failure_context(str(exc), source)
    raise
