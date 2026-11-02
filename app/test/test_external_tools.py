import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import get_public_holidays


result = get_public_holidays(
    country_code="ES",
    year=2026
)

print(result)