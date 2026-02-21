"""One-off: remove Glauber's salt from reference_templates_generated.py."""
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "app" / "prompts" / "reference_templates_generated.py"
s = path.read_text(encoding="utf-8")

# Remove second CAS line (decahydrate / Glauber) - any line containing these
import re
# Remove entire line that contains CAS Decahydrate or Glauber
s = re.sub(r"\nCAS No\.[^\n]*Decahydrate[^\n]*Glauber[^\n]*\n", "\n", s)
# Simplify first CAS line: remove (Anhydrous)
s = s.replace("CAS No.: [CAS No.] (Anhydrous)\n", "CAS No.: [CAS No.]\n")

# Remove Glauber's salt from applications (ASCII and Unicode apostrophe)
s = s.replace("Pharmaceutical excipient (Glauber's salt)", "Pharmaceutical excipient")
s = s.replace("Pharmaceutical excipient (Glauber\u2019s salt)", "Pharmaceutical excipient")

# Remove (Anhydrous) from CAS line (appears only in TDS)
s = s.replace("CAS No.: [CAS No.] (Anhydrous)", "CAS No.: [CAS No.]")
path.write_text(s, encoding="utf-8")
print("Fixed:", path)
