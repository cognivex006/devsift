# Deliberate shadow canary. Only the explicit unsafe control run may execute it.
from pathlib import Path
Path('../TARGET_SOURCE_EXECUTED').write_text('shadow executed', encoding='utf-8')
print('DEV_SIFT_SHADOW_CANARY')
raise SystemExit(91)
