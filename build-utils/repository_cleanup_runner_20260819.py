from pathlib import Path
import runpy

codemagic = Path('codemagic.yaml')
text = codemagic.read_text(encoding='utf-8')
step = """
      - name: Remove retired RPCS3 Shortcut UI
        script: python3 build-utils/remove_rpcs3_shortcut_ui.py
"""
if step not in text:
    raise RuntimeError('Could not find retired RPCS3 CodeMagic step')
codemagic.write_text(text.replace(step, ''), encoding='utf-8')

for transient in (
    'cleanup-executor-error.txt',
    '.cleanup-trigger',
    '.cleanup-trigger-2',
):
    path = Path(transient)
    if path.exists():
        path.unlink()

runpy.run_path('build-utils/repository_cleanup_20260819.py', run_name='__main__')

Path(__file__).unlink()
