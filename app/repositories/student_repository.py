"""
Module Name: student_repository.py

Purpose:
    Data access for the Student entity. All queries run inside
    DatabaseManager.session(), which handles commit/rollback/close —
    this repository never opens its own connection or engine.

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from typing import Optional

from core.database_manager import DatabaseManager
from core.logging_manager import get_logger

from app.models.orm_models import Student

log = get_logger(__name__)


class StudentRepository:
    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def get_by_id(self, student_id: str) -> Optional[Student]:
        with self._db.session() as sess:
            student = sess.get(Student, student_id)
            if student:
                sess.expunge(student)
            return student

    def list_active(self) -> list[Student]:
        with self._db.session() as sess:
            students = (
                sess.query(Student)
                .filter(Student.is_active == 1)
                .order_by(Student.student_name)
                .all()
            )
            for s in students:
                sess.expunge(s)
            return students
