"""Read authorized local files without changing the original CSVs."""
from pathlib import Path

import pandas as pd

REQUIRED = {
    "date", "card_id", "card_name", "card_number", "set_name", "language",
    "grade", "currency", "source_url", "collected_at",
}
OPTIONAL = ["marketplace", "sale_type", "sale_id", "cert_number", "price_usd", "original_price",
            "fx_rate_to_usd", "fx_rate_date", "fx_source_url"]


def load_csvs(directory: Path, pattern: str, source: str, data_type: str) -> pd.DataFrame:
    frames = []
    for path in sorted(directory.glob(pattern)):
        try:
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        except (ValueError, OSError) as exc:
            raise ValueError(f"{path.name}: CSV 읽기 실패 ({exc})") from exc
        missing = REQUIRED - set(frame.columns)
        if not {"price_usd", "original_price"}.intersection(frame.columns):
            missing.add("price_usd 또는 original_price")
        if missing:
            raise ValueError(f"{path.name}: 필수 열 누락 {', '.join(sorted(missing))}")
        for column in OPTIONAL:
            if column not in frame:
                frame[column] = ""
        frame = frame[sorted(REQUIRED) + OPTIONAL].copy()
        frame["source"] = source
        frame["data_type"] = data_type
        frame["input_file"] = path.name
        frames.append(frame)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame(columns=sorted(REQUIRED) + OPTIONAL + ["source", "data_type", "input_file"])
