from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict, Any


class CategoryEnum(str, Enum):
    VISUAL_OBJECTS_AND_SCENES = "visual_objects_and_scenes"
    PEOPLE_AND_ATTRIBUTES = "people_and_attributes"
    OCR_DEPENDENT = "ocr_dependent"
    ASR_DEPENDENT = "asr_dependent"
    ACTIONS = "actions"
    TEMPORAL = "temporal"
    COMBINED = "combined"
    HARD_NEGATIVES = "hard_negatives"


class ExpectedModalityEnum(str, Enum):
    IMAGE_CLIP = "image_clip"
    OCR = "ocr"
    ASR = "asr"


class FailureReasonEnum(str, Enum):
    MISSING_VISUAL_FEATURE = "missing_visual_feature"
    MISSING_OCR_TEXT = "missing_ocr_text"
    ASR_TRANSCRIPTION_ERROR = "asr_transcription_error"
    INCORRECT_TIMESTAMP_ALIGNMENT = "incorrect_timestamp_alignment"
    POOR_FRAME_SAMPLING = "poor_frame_sampling"
    FEATURE_DILUTION = "feature_dilution"
    SCORE_CALIBRATION_PROBLEM = "score_calibration_problem"
    FUSION_PROBLEM = "fusion_problem"
    DUPLICATE_RESULTS = "duplicate_results"
    QUERY_TOO_AMBIGUOUS = "query_too_ambiguous"
    ANNOTATION_OR_GROUND_TRUTH_ERROR = "annotation_or_ground_truth_error"
    TEMPORAL_UNDERSTANDING_REQUIRED = "temporal_understanding_required"
    CORRECT_RESULT_OUTSIDE_TOP_20 = "correct_result_outside_top_20"
    HIGH_LATENCY_OR_TIMEOUT = "high_latency_or_timeout"
    NONE = "none"


@dataclass
class QuerySample:
    query_id: str
    query: str
    primary_category: str
    secondary_categories: List[str] = field(default_factory=list)
    expected_modalities: List[str] = field(default_factory=lambda: ["image_clip"])
    correct_video_id: str = ""
    correct_start_time: float = 0.0
    correct_end_time: float = 0.0
    source: str = "previous_challenge"
    difficulty: str = "medium"
    validated: bool = False
    notes: str = ""

    def validate_schema(self) -> List[str]:
        errors = []
        if not self.query_id:
            errors.append("query_id is required.")
        if not self.query:
            errors.append("query text is required.")
        if self.primary_category not in [c.value for c in CategoryEnum]:
            errors.append(f"Invalid primary_category: '{self.primary_category}'. Must be one of {[c.value for c in CategoryEnum]}.")
        for m in self.expected_modalities:
            if m not in [em.value for em in ExpectedModalityEnum]:
                errors.append(f"Invalid expected_modality '{m}'. Allowed: {[em.value for em in ExpectedModalityEnum]} (VideoCLIP is deprecated).")
        if not self.correct_video_id:
            errors.append("correct_video_id is required.")
        if self.correct_start_time > self.correct_end_time:
            errors.append(f"correct_start_time ({self.correct_start_time}) cannot be greater than correct_end_time ({self.correct_end_time}).")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuerySample":
        return cls(
            query_id=data.get("query_id", ""),
            query=data.get("query", ""),
            primary_category=data.get("primary_category", "visual_objects_and_scenes"),
            secondary_categories=data.get("secondary_categories", []),
            expected_modalities=data.get("expected_modalities", ["image_clip"]),
            correct_video_id=data.get("correct_video_id", ""),
            correct_start_time=float(data.get("correct_start_time", 0.0)),
            correct_end_time=float(data.get("correct_end_time", 0.0)),
            source=data.get("source", "previous_challenge"),
            difficulty=data.get("difficulty", "medium"),
            validated=bool(data.get("validated", False)),
            notes=data.get("notes", ""),
        )


@dataclass
class RetrievedCandidate:
    rank: int
    video_id: str
    frame_id: int
    timestamp_sec: float
    distance_or_score: float
    time_line: List[int] = field(default_factory=list)


@dataclass
class QueryResult:
    query_id: str
    query: str
    primary_category: str
    expected_modalities: List[str]
    correct_video_id: str
    correct_timestamp: float
    correct_result_rank: Optional[int]
    top_1_correct: bool
    top_5_correct: bool
    top_20_correct: bool
    latency_ms: float
    failure_reason: str
    top_1_result: Optional[Dict[str, Any]] = None
    top_5_results: List[Dict[str, Any]] = field(default_factory=list)
    top_20_results: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AggregatedMetrics:
    total_queries: int = 0
    recall_at_1: float = 0.0
    recall_at_5: float = 0.0
    recall_at_20: float = 0.0
    mrr: float = 0.0
    median_rank: float = 0.0
    avg_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
