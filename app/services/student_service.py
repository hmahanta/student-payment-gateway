"""
Module Name: student_service.py

Purpose:
    Business logic for student profile lookups.

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from core.logging_manager import get_logger

from app.exceptions import StudentNotFoundError
from app.models.orm_models import Student
from app.repositories.student_repository import StudentRepository

log = get_logger(__name__)


class StudentService:
    def __init__(
        self,
        student_repository: StudentRepository,
        # future managers — optional, wired in later without signature changes
        cache_manager: object | None = None,
        audit_manager: object | None = None,
    ) -> None:
        self._repo = student_repository
        self._cache = cache_manager
        self._audit = audit_manager

    def get_student(self, student_id: str) -> Student:
        student = self._repo.get_by_id(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)
        return student

    def list_active_students(self) -> list[Student]:
        return self._repo.list_active()
