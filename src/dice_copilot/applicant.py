from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path


_GENERIC_TITLE_WORDS = {
    "application", "applications", "architect", "developer", "engineer",
    "cloud", "engineering", "full", "lead", "platform", "principal", "role",
    "roles", "senior", "software", "specialist", "stack", "staff",
}
_REGEX_ARTIFACTS = {"b", "d", "s", "w"}


@dataclass(frozen=True)
class Applicant:
    first_name: str
    last_name: str
    email: str
    phone: str
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = "United States"
    resume_path: str = ""
    resume_folder: str = ""
    resume_rules: list[dict[str, str]] = field(default_factory=list)
    authorized_to_work: bool | None = None
    requires_sponsorship: bool | None = None
    years_experience: str = ""
    answers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Applicant":
        if not path.exists():
            raise ValueError(f"Applicant profile not found: {path}. Copy applicant.example.json to applicant.json and edit it.")
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {name for name in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown applicant keys: {', '.join(sorted(unknown))}")
        applicant = cls(**data)
        applicant.validate(path.parent)
        return applicant

    def validate(self, base: Path) -> None:
        missing = [name for name in ("first_name", "last_name", "email", "phone") if not getattr(self, name)]
        if not self.resume_path and not self.resume_rules:
            missing.append("resume_path or resume_rules")
        if missing:
            raise ValueError(f"Missing applicant values: {', '.join(missing)}")
        if "@" not in self.email:
            raise ValueError("Applicant email is invalid")
        if self.resume_path:
            self._validate_resume(self.resume(base))
        if self.resume_rules:
            folder = self.resume_directory(base)
            if not folder.is_dir():
                raise ValueError(f"Resume folder does not exist: {folder}")
            for index, rule in enumerate(self.resume_rules, start=1):
                if set(rule) != {"title_pattern", "file"} or not all(isinstance(value, str) and value for value in rule.values()):
                    raise ValueError(f"Resume rule {index} must contain non-empty title_pattern and file values")
                try:
                    re.compile(rule["title_pattern"], re.I)
                except re.error as exc:
                    raise ValueError(f"Invalid title pattern in resume rule {index}: {exc}") from exc
                self._validate_resume(self._rule_path(folder, rule["file"]))

    def resume(self, base: Path) -> Path:
        path = Path(self.resume_path).expanduser()
        return path if path.is_absolute() else (base / path).resolve()

    def resume_directory(self, base: Path) -> Path:
        folder = Path(self.resume_folder).expanduser() if self.resume_folder else base
        return folder.resolve() if folder.is_absolute() else (base / folder).resolve()

    @staticmethod
    def _validate_resume(path: Path) -> None:
        if not path.is_file() or path.suffix.lower() not in {".pdf", ".doc", ".docx"}:
            raise ValueError(f"Resume must be an existing PDF or Word file: {path}")

    @staticmethod
    def _rule_path(folder: Path, filename: str) -> Path:
        candidate = (folder / filename).resolve()
        try:
            candidate.relative_to(folder)
        except ValueError as exc:
            raise ValueError(f"Resume rule file must stay inside resume_folder: {filename}") from exc
        return candidate

    def resume_for(self, job_title: str, base: Path, job_description: str = "") -> Path:
        folder = self.resume_directory(base)
        best_rule, best_score = self._best_resume_rule(job_title)
        if job_description and best_score < 100:
            context_rule, context_score = self._best_resume_rule(f"{job_title}\n{job_description}")
            if context_score >= 100 and context_score > best_score:
                best_rule, best_score = context_rule, context_score
        if best_rule is not None and best_score >= 50:
            resume = self._rule_path(folder, best_rule["file"])
            self._validate_resume(resume)
            return resume
        if self.resume_path:
            resume = self.resume(base)
            self._validate_resume(resume)
            return resume
        raise ValueError(f"No resume rule matched job title: {job_title}")

    def _best_resume_rule(self, text: str) -> tuple[dict[str, str] | None, float]:
        best_rule: dict[str, str] | None = None
        best_score = 0.0
        for rule in self.resume_rules:
            score = self._title_match_score(text, rule)
            if score > best_score:
                best_rule = rule
                best_score = score
        return best_rule, best_score

    @staticmethod
    def _title_words(value: str) -> list[str]:
        value = value.lower().replace("\\.net", " dotnet ").replace(".net", " dotnet ")
        return [
            word for word in re.findall(r"[a-z0-9]+(?:[+#][a-z0-9]*)?", value)
            if word not in _REGEX_ARTIFACTS
        ]

    @classmethod
    def _pattern_alternatives(cls, pattern: str) -> list[str]:
        """Expand simple regex groups, then return keyword alternatives."""
        grouped = re.search(r"\(\?:([^()]+)\)", pattern)
        if grouped:
            prefix = pattern[:grouped.start()]
            suffix = pattern[grouped.end():]
            expanded: list[str] = []
            for option in grouped.group(1).split("|"):
                expanded.extend(cls._pattern_alternatives(prefix + option + suffix))
            return expanded
        return [alternative for alternative in pattern.split("|") if alternative]

    @classmethod
    def _title_match_score(cls, job_title: str, rule: dict[str, str]) -> float:
        """Score all rules so the most specific keyword combination wins."""
        title_words = cls._title_words(job_title)
        if not title_words:
            return 0.0
        title_candidates = set(title_words)
        title_candidates.update(
            title_words[index] + title_words[index + 1]
            for index in range(len(title_words) - 1)
        )

        keyword_score = 0.0
        for alternative in cls._pattern_alternatives(rule["title_pattern"]):
            matched: list[tuple[str, bool]] = []
            for keyword in set(cls._title_words(alternative)):
                generic = keyword in _GENERIC_TITLE_WORDS
                if keyword in title_candidates:
                    matched.append((keyword, generic))
                    continue
                if len(keyword) >= 5 and any(
                    len(candidate) >= 5 and SequenceMatcher(None, keyword, candidate).ratio() >= 0.86
                    for candidate in title_candidates
                ):
                    matched.append((keyword, generic))

            distinctive_words = {
                keyword for keyword in set(cls._title_words(alternative))
                if keyword not in _GENERIC_TITLE_WORDS
            }
            distinctive_matches = sum(not generic for _, generic in matched)
            alternative_score = sum(5 if generic else 70 for _, generic in matched)
            if len(matched) > 1:
                alternative_score += 30 * (len(matched) - 1)
            if distinctive_matches and distinctive_matches == len(distinctive_words):
                keyword_score = max(keyword_score, alternative_score)

        regex_score = 0.0
        regex_match = re.search(rule["title_pattern"], job_title, re.I)
        if regex_match:
            matched_words = cls._title_words(regex_match.group(0))
            regex_score = 90 + min(len(regex_match.group(0)), 40) + 10 * len(matched_words)

        return max(keyword_score, regex_score)

    def field_values(self) -> list[tuple[str, str]]:
        values = [
            (r"first\s*name", self.first_name),
            (r"last\s*name|surname", self.last_name),
            (r"e-?mail", self.email),
            (r"phone|mobile", self.phone),
            (r"city", self.city),
            (r"state|province", self.state),
            (r"zip|postal", self.postal_code),
            (r"country", self.country),
            (r"years?.*(experience)|experience.*years?", self.years_experience),
        ]
        return [(pattern, value) for pattern, value in values if value]
