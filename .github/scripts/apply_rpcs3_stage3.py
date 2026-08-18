from __future__ import annotations

import base64
import re
import subprocess
import zlib
from pathlib import Path


SCRIPT_PATH = Path('.github/scripts/apply_rpcs3_stage3.py')
SWIFT_PATH = Path(
    'packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift'
)
PAYLOAD_PATTERN = re.compile(r"b64decode\('([^']+)'\)")


def _load_original_payload() -> str:
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


def _normalize_current_swift_for_generator() -> None:
    text = SWIFT_PATH.read_text(encoding='utf-8')
    current_query_block = '''        var components = URLComponents()
        components.scheme = "stikjit"
        components.host = "enable-jit"
        var queryItems = [URLQueryItem(name: "bundle-id", value: targetBundleId)]
        if !scriptName.isEmpty {
            queryItems.append(URLQueryItem(name: "script-name", value: scriptName))
        }
        components.queryItems = queryItems
'''
    normalized_query_block = '''        var components = URLComponents()
        components.scheme = "stikjit"
        components.host = "enable-jit"
        components.queryItems = [
            URLQueryItem(name: "bundle-id", value: targetBundleId),
            URLQueryItem(name: "script-name", value: scriptName),
        ]
'''
    if current_query_block in text:
        text = text.replace(current_query_block, normalized_query_block, 1)
    elif normalized_query_block not in text:
        raise SystemExit('Could not normalize the current native preflight query block')
    SWIFT_PATH.write_text(text, encoding='utf-8')


def _adapt_generator(generator: str) -> str:
    # Preserve Android-name scraping in the current service while adding RPCS3.
    old_manual_marker = (
        '"          gameName: isMeloNxVirtual ? gameName : null,\\n",'
    )
    new_manual_marker = (
        '"          gameName: (systemFolder == \'android\' || isMeloNxVirtual)\\n'
        '              ? gameName\\n'
        '              : null,\\n",'
    )
    if generator.count(old_manual_marker) != 1:
        raise SystemExit(
            'Expected exactly one old manual marker, '
            f'found {generator.count(old_manual_marker)}'
        )
    generator = generator.replace(old_manual_marker, new_manual_marker, 1)

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
    if generator.count(old_generated_marker) != 1:
        raise SystemExit(
            'Expected exactly one generated manual marker, '
            f'found {generator.count(old_generated_marker)}'
        )
    generator = generator.replace(old_generated_marker, new_generated_marker, 1)

    # The current native plugin validates a non-empty launch URL in its guard.
    # Stage 3 also supports foregrounding a bundle with no app-specific URL, so
    # make the generator match the current guard before replacing it.
    old_guard_fragment = (
        '"            let rawLaunch = args[\\"launchUrl\\"] as? String,\\n"\n'
        '    "            let launchURL = URL(string: rawLaunch),\\n"'
    )
    current_guard_fragment = (
        '"            let rawLaunch = args[\\"launchUrl\\"] as? String,\\n"\n'
        '    "            !rawLaunch.isEmpty,\\n"\n'
        '    "            let launchURL = URL(string: rawLaunch),\\n"'
    )
    if generator.count(old_guard_fragment) != 1:
        raise SystemExit(
            'Expected exactly one native guard fragment, '
            f'found {generator.count(old_guard_fragment)}'
        )
    generator = generator.replace(old_guard_fragment, current_guard_fragment, 1)

    # In the current plugin targetBundleId is resolved before the URLComponents
    # block. Insert the generated delayed-launch URL there, not before the
    # earlier scriptName declaration.
    old_launch_marker = (
        'launch_marker = "        let scriptName = '
        '(args[\\"scriptName\\"] as? String) ?? \\"universal.js\\"\\n"'
    )
    new_launch_marker = (
        'launch_marker = "        var components = URLComponents()\\n"'
    )
    if generator.count(old_launch_marker) != 1:
        raise SystemExit(
            'Expected exactly one native launch marker declaration, '
            f'found {generator.count(old_launch_marker)}'
        )
    generator = generator.replace(old_launch_marker, new_launch_marker, 1)

    # The current plugin names its preflight URLComponents value `components`.
    generator = generator.replace('preflightComponents', 'components')
    return generator


def _polish_generated_swift() -> None:
    text = SWIFT_PATH.read_text(encoding='utf-8')
    text = text.replace(
        '+ "Game URL: \\(rawLaunch)"',
        '+ "Delayed URL: \\(launchURL.absoluteString)"',
    )
    text = text.replace(
        'message: "openUrlAfterJitPreflight requires launchUrl and targetBaseBundleId"',
        'message: "openUrlAfterJitPreflight requires targetBaseBundleId and a valid launch mode"',
    )
    SWIFT_PATH.write_text(text, encoding='utf-8')


payload = _load_original_payload()
source = zlib.decompress(base64.b64decode(payload)).decode('utf-8')
source = _adapt_generator(source)
_normalize_current_swift_for_generator()

try:
    exec(compile(source, '<rpcs3-stage3>', 'exec'))
except SystemExit as exc:
    _print_failure_context(str(exc), source)
    raise

_polish_generated_swift()
