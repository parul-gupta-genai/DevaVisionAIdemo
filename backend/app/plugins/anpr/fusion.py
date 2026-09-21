from typing import List, Dict, Optional, Tuple
from collections import defaultdict, Counter

class OcrObservation:
    def __init__(self, text: str, confidence: float, timestamp: float):
        self.text = text
        self.confidence = confidence
        self.timestamp = timestamp

class TemporalFusion:
    """
    Accumulates OCR observations for a tracked vehicle and fuses them to
    determine the most probable license plate.

    Two-stage fusion:
      1. Per-character weighted voting across observations of the modal
         length — recovers the correct plate even when no single frame read
         it perfectly.
      2. Falls back to whole-string weighted voting when the fused candidate
         fails validation.
    """
    def __init__(self):
        self.observations: List[OcrObservation] = []

    def add_observation(self, text: str, confidence: float, timestamp: float):
        self.observations.append(OcrObservation(text, confidence, timestamp))

    def _whole_string_vote(self) -> Tuple[Optional[str], float]:
        plate_scores: Dict[str, float] = defaultdict(float)
        for obs in self.observations:
            plate_scores[obs.text] += obs.confidence
        if not plate_scores:
            return None, 0.0
        winning_plate = max(plate_scores.items(), key=lambda x: x[1])[0]
        winning_votes = [o.confidence for o in self.observations if o.text == winning_plate]
        avg_confidence = sum(winning_votes) / len(winning_votes) if winning_votes else 0.0
        return winning_plate, avg_confidence

    def _char_position_vote(self) -> Tuple[Optional[str], float]:
        """Weighted per-character vote among observations of the modal length."""
        lengths = Counter(len(o.text) for o in self.observations)
        if not lengths:
            return None, 0.0
        # Prefer the most common length; break ties toward the longer read
        modal_len = max(lengths.items(), key=lambda x: (x[1], x[0]))[0]
        group = [o for o in self.observations if len(o.text) == modal_len]
        if len(group) < 2:
            return None, 0.0

        fused_chars = []
        char_confs = []
        for i in range(modal_len):
            votes: Dict[str, float] = defaultdict(float)
            for o in group:
                votes[o.text[i]] += o.confidence
            best_char, best_score = max(votes.items(), key=lambda x: x[1])
            total = sum(votes.values())
            fused_chars.append(best_char)
            char_confs.append(best_score / total if total > 0 else 0.0)

        fused = "".join(fused_chars)
        avg_conf = sum(char_confs) / len(char_confs) if char_confs else 0.0
        # Scale by the average observation confidence of the group so a fused
        # result from low-quality reads doesn't outrank a clean single read.
        group_conf = sum(o.confidence for o in group) / len(group)
        return fused, avg_conf * group_conf

    def get_best_plate(self) -> Tuple[Optional[str], float]:
        from app.plugins.anpr.config_parser import anpr_app_config

        if len(self.observations) < anpr_app_config.fusion.min_observations:
            return None, 0.0

        whole_plate, whole_conf = self._whole_string_vote()
        if whole_plate is None:
            return None, 0.0

        fused_plate, fused_conf = self._char_position_vote()
        if fused_plate and fused_plate != whole_plate:
            # Only prefer the character-fused candidate when it validates
            from app.plugins.anpr.validator import PlateValidator
            is_valid, repaired = PlateValidator.repair_and_validate(fused_plate)
            if is_valid and repaired and fused_conf >= whole_conf * 0.8:
                return repaired, max(fused_conf, whole_conf)

        return whole_plate, whole_conf
