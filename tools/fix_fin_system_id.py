from pathlib import Path

path = Path(__file__).resolve().parents[1] / "lib/services/fin_library_service.dart"
text = path.read_text(encoding="utf-8")
old = "final systems = <String, int>{"
new = "final systems = <String, String>{"
if old not in text:
    raise RuntimeError("Fin system map anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Fin system ID types aligned with SystemModel.id.")
