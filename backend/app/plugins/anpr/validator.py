import re
from typing import Tuple, Optional
from app.plugins.anpr.config_parser import anpr_app_config

class PlateValidator:
    """
    Validates and repairs Indian license plates.

    Standard format:  SS RR C[CC] NNNN  (state, RTO district, series, number)
    BH series:        YY BH NNNN C[C]
    Diplomatic:       NNN CD/CC NNNN
    Military:         ^ YY C NNNNNN C
    """

    # All valid Indian state/UT registration codes (incl. legacy OR/UA and
    # merged DD/DN), per MoRTH.
    STATE_CODES = {
        "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA",
        "GJ", "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML",
        "MN", "MP", "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN",
        "TR", "TS", "TG", "UK", "UA", "UP", "WB",
    }

    CHAR_TO_NUM = {
        'O': '0', 'Q': '0', 'D': '0',
        'I': '1', 'L': '1', 'T': '1',
        'Z': '2', 'B': '8', 'S': '5',
        'A': '4', 'G': '6', 'J': '3'
    }

    NUM_TO_CHAR = {
        '0': 'O', '1': 'I', '2': 'Z',
        '8': 'B', '5': 'S', '4': 'A', '6': 'G'
    }

    STRATEGIES = {
        "private": re.compile(r'^([A-Z]{2})([0-9]{1,2})([A-Z]{1,3})([0-9]{4})$'),
        "commercial": re.compile(r'^([A-Z]{2})([0-9]{1,2})([A-Z]{1,3})([0-9]{4})$'),
        "ev": re.compile(r'^([A-Z]{2})([0-9]{1,2})([A-Z]{1,3})([0-9]{4})$'),
        "diplomatic": re.compile(r'^([0-9]{1,3})(CD|CC|UN)([0-9]{1,4})$'),
        "military": re.compile(r'^↑?([0-9]{2})([A-Z])([0-9]{4,6})([A-Z])$'),
        "bh_series": re.compile(r'^([0-9]{2})BH([0-9]{4})([A-Z]{1,2})$'),
        # Older plates without a series letter (e.g. DL 4 1234)
        "legacy_no_series": re.compile(r'^([A-Z]{2})([0-9]{1,2})([0-9]{4})$'),
    }

    @classmethod
    def clean_plate_string(cls, text: str) -> str:
        cleaned = re.sub(r'[^\w↑]', '', text.upper())
        # HSRP plates carry a vertical "IND" marker that OCR often prepends.
        if len(cleaned) > 7 and cleaned.startswith("IND"):
            cleaned = cleaned[3:]
        return cleaned

    @classmethod
    def _fix_segment(cls, segment: str, expected_type: str) -> str:
        fixed = []
        for char in segment:
            if expected_type == 'char' and char.isdigit():
                fixed.append(cls.NUM_TO_CHAR.get(char, char))
            elif expected_type == 'num' and char.isalpha():
                fixed.append(cls.CHAR_TO_NUM.get(char, char))
            else:
                fixed.append(char)
        return "".join(fixed)

    @classmethod
    def _matches(cls, candidate: str, active_strategies) -> bool:
        for strategy in active_strategies:
            regex = cls.STRATEGIES.get(strategy)
            if not regex:
                continue
            m = regex.match(candidate)
            if not m:
                continue
            # Standard formats must start with a real state code
            if strategy in ("private", "commercial", "ev", "legacy_no_series"):
                if candidate[:2] not in cls.STATE_CODES:
                    continue
            return True
        return False

    @classmethod
    def repair_and_validate(cls, raw_plate: str, confidence: float = 1.0) -> Tuple[bool, Optional[str]]:
        cleaned = cls.clean_plate_string(raw_plate)
        if not cleaned:
            return False, None

        active_strategies = anpr_app_config.validation.format_strategies

        # 1. Exact match against active strategies
        if cls._matches(cleaned, active_strategies):
            return True, cleaned

        # 2. Position-aware repair for the standard SS RR C[CC] NNNN layout
        if anpr_app_config.validation.smart_repair_enabled:
            std_enabled = any(s in active_strategies for s in ("private", "commercial", "ev"))
            if std_enabled and 7 <= len(cleaned) <= 11:
                state_part = cls._fix_segment(cleaned[:2], 'char')
                num_part = cls._fix_segment(cleaned[-4:], 'num')
                middle_part = cleaned[2:-4]

                for rto_len in (2, 1):
                    if rto_len >= len(middle_part):
                        continue  # need at least one series letter left over
                    rto_part = cls._fix_segment(middle_part[:rto_len], 'num')
                    series_part = cls._fix_segment(middle_part[rto_len:], 'char')
                    candidate = f"{state_part}{rto_part}{series_part}{num_part}"
                    if cls._matches(candidate, active_strategies):
                        return True, candidate

            # BH-series repair: YY BH NNNN C[C]
            if "bh_series" in active_strategies and 8 <= len(cleaned) <= 10:
                year_part = cls._fix_segment(cleaned[:2], 'num')
                rest = cleaned[2:]
                if rest[:2] in ("BH", "8H", "B4"):
                    tail = rest[2:]
                    if len(tail) >= 5:
                        num_part = cls._fix_segment(tail[:4], 'num')
                        series_part = cls._fix_segment(tail[4:], 'char')
                        candidate = f"{year_part}BH{num_part}{series_part}"
                        if cls.STRATEGIES["bh_series"].match(candidate):
                            return True, candidate

        # 3. Optional lenient mode (disabled by default): accept any 6+ char
        #    alphanumeric string. Kept for non-Indian deployments.
        if not anpr_app_config.validation.strict and len(cleaned) >= 6:
            return True, cleaned

        return False, cleaned
