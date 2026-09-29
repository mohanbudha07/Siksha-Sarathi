"""Private Learning Material upload-storage regression tests."""

import io
import importlib
import re
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from pathlib import Path
from zoneinfo import ZoneInfo

from werkzeug.datastructures import FileStorage

from backend.learning_materials import (
    MAX_MATERIAL_FILE_BYTES,
    MaterialUploadError,
    configure_learning_material_upload_root,
    finalize_staged_material_uploads,
    safe_storage_path,
    stage_material_uploads,
)
from backend.time_utils import serialize_nepal_datetime

try:
    fixture = importlib.import_module("test_quiz_statistics")
except ModuleNotFoundError:
    fixture = importlib.import_module("backend.tests.test_quiz_statistics")


def upload(name, content=b"sample", content_type="application/octet-stream"):
    return FileStorage(
        stream=io.BytesIO(content),
        filename=name,
        content_type=content_type,
    )


class NepalDateTimeTests(unittest.TestCase):
    def test_naive_mysql_datetime_is_interpreted_as_nepal_local_time(self):
        value = datetime(2026, 9, 30, 0, 59, 8)
        self.assertEqual(
            serialize_nepal_datetime(value),
            "Sep 30, 2026, 12:59 AM NPT",
        )

    def test_aware_utc_datetime_converts_to_nepal_time(self):
        value = datetime(2026, 9, 29, 19, 14, 8, tzinfo=timezone.utc)
        self.assertEqual(
            serialize_nepal_datetime(value),
            "Sep 30, 2026, 12:59 AM NPT",
        )

    def test_aware_nepal_datetime_remains_correct(self):
        value = datetime(
            2026, 9, 30, 0, 59, 8, tzinfo=ZoneInfo("Asia/Kathmandu")
        )
        self.assertEqual(
            serialize_nepal_datetime(value),
            "Sep 30, 2026, 12:59 AM NPT",
        )

    def test_iso_datetime_strings_preserve_or_convert_timezone_correctly(self):
        self.assertEqual(
            serialize_nepal_datetime("2026-09-29T19:14:08+00:00"),
            "Sep 30, 2026, 12:59 AM NPT",
        )
        self.assertEqual(
            serialize_nepal_datetime("2026-09-30T00:59:08"),
            "Sep 30, 2026, 12:59 AM NPT",
        )

    def test_none_remains_none(self):
        self.assertIsNone(serialize_nepal_datetime(None))


class LearningMaterialStorageTests(unittest.TestCase):
    def test_relative_upload_configuration_resolves_from_repository_root(self):
        with tempfile.TemporaryDirectory() as temporary_directory, patch.dict(
            "os.environ", {"LEARNING_MATERIAL_UPLOAD_DIR": "private/materials"}
        ):
            upload_root = configure_learning_material_upload_root(temporary_directory)
            self.assertEqual(
                Path(upload_root),
                Path(temporary_directory) / "private" / "materials",
            )
            self.assertFalse(Path(upload_root).exists())
            stage_material_uploads([upload("lesson.pdf")], upload_root)
            self.assertTrue(Path(upload_root).is_dir())

    def test_text_only_material_does_not_create_upload_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            upload_root = Path(temporary_directory) / "private-materials"
            self.assertEqual(stage_material_uploads([], upload_root), [])
            self.assertFalse(upload_root.exists())

    def test_pdf_docx_and_pptx_are_staged_and_finalized_with_generated_keys(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            files = stage_material_uploads([
                upload("lesson.pdf", b"pdf", "application/pdf"),
                upload("lesson.docx", b"docx"),
                upload("lesson.pptx", b"pptx"),
            ], temporary_directory)

            self.assertEqual([item["original_filename"] for item in files], [
                "lesson.pdf", "lesson.docx", "lesson.pptx",
            ])
            self.assertEqual(len({item["stored_filename"] for item in files}), 3)
            self.assertTrue(all(
                Path(item["stored_filename"]).name == item["stored_filename"]
                for item in files
            ))
            finalize_staged_material_uploads(temporary_directory, files)
            for item, expected in zip(files, (b"pdf", b"docx", b"pptx")):
                stored_path = safe_storage_path(
                    temporary_directory, item["stored_filename"]
                )
                self.assertEqual(stored_path.read_bytes(), expected)
                self.assertFalse(safe_storage_path(
                    temporary_directory, item["staging_filename"]
                ).exists())

    def test_unsupported_extension_is_rejected_and_staging_is_cleaned(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(MaterialUploadError, "file type"):
                stage_material_uploads([
                    upload("valid.pdf"), upload("malware.exe", b"not executable")
                ], temporary_directory)
            self.assertEqual(list(Path(temporary_directory).iterdir()), [])

    def test_oversized_file_is_rejected_and_staging_is_cleaned(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            oversized = b"x" * (MAX_MATERIAL_FILE_BYTES + 1)
            with self.assertRaisesRegex(MaterialUploadError, "25 MB"):
                stage_material_uploads([upload("large.pdf", oversized)], temporary_directory)
            self.assertEqual(list(Path(temporary_directory).iterdir()), [])

    def test_more_than_ten_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(MaterialUploadError, "at most 10"):
                stage_material_uploads(
                    [upload(f"{index}.pdf") for index in range(11)],
                    temporary_directory,
                )
            self.assertEqual(list(Path(temporary_directory).iterdir()), [])

    def test_path_traversal_filename_is_sanitized_and_stays_in_private_root(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            files = stage_material_uploads(
                [upload("../../outside.pdf", b"private")], temporary_directory
            )
            self.assertEqual(files[0]["original_filename"], "outside.pdf")
            finalize_staged_material_uploads(temporary_directory, files)
            stored_path = safe_storage_path(
                temporary_directory, files[0]["stored_filename"]
            )
            self.assertEqual(stored_path.parent, Path(temporary_directory).resolve())
            self.assertTrue(stored_path.exists())

    def test_non_ascii_filename_with_allowed_extension_uses_generated_storage_key(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            files = stage_material_uploads(
                [upload("नेपाली पाठ.pdf", b"pdf")], temporary_directory
            )
            self.assertEqual(files[0]["original_filename"], "document.pdf")
            self.assertRegex(files[0]["stored_filename"], re.compile(r"^[0-9a-f]{32}\.pdf$"))
            finalize_staged_material_uploads(temporary_directory, files)
            stored_path = safe_storage_path(
                temporary_directory, files[0]["stored_filename"]
            )
            self.assertEqual(stored_path.read_bytes(), b"pdf")
            self.assertEqual(stored_path.parent, Path(temporary_directory).resolve())

    def test_duplicate_original_names_receive_distinct_storage_names(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            files = stage_material_uploads([
                upload("same.pdf", b"first"), upload("same.pdf", b"second"),
            ], temporary_directory)
            finalize_staged_material_uploads(temporary_directory, files)
            self.assertEqual(files[0]["original_filename"], files[1]["original_filename"])
            self.assertNotEqual(files[0]["stored_filename"], files[1]["stored_filename"])
            self.assertEqual(
                safe_storage_path(temporary_directory, files[0]["stored_filename"]).read_bytes(),
                b"first",
            )
            self.assertEqual(
                safe_storage_path(temporary_directory, files[1]["stored_filename"]).read_bytes(),
                b"second",
            )

    def test_path_guard_rejects_traversal_and_external_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary_directory, tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(ValueError):
                safe_storage_path(temporary_directory, "../outside.pdf")
            outside_file = Path(outside) / "external.pdf"
            outside_file.touch()
            (Path(temporary_directory) / "link.pdf").symlink_to(outside_file)
            with self.assertRaises(ValueError):
                safe_storage_path(temporary_directory, "link.pdf")

    def test_migration_and_fresh_schema_contract(self):
        backend_root = Path(__file__).resolve().parents[1]
        migration = (backend_root / "migrations" / "019_learning_material_attachments.sql").read_text()
        setup_schema = (backend_root / "setup_db.sql").read_text()
        for source in (migration, setup_schema):
            self.assertIn("target_class_id INT NULL", source)
            self.assertIn("target_student_id INT NULL", source)
            self.assertIn("note_attachments", source)
            self.assertIn("idx_notes_target_class", source)
            self.assertIn("idx_notes_target_student", source)
            self.assertIn("fk_notes_target_class", source)
            self.assertIn("fk_notes_target_student", source)
            normalized_source = " ".join(source.split()).lower()
            self.assertIn(
                "constraint chk_notes_student_requires_class check "
                "(target_student_id is null or target_class_id is not null)",
                normalized_source,
            )
        self.assertIn("FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE", migration)
        self.assertIn("INDEX idx_note_attachments_note_id (note_id)", migration)
        self.assertIn("information_schema.table_constraints", migration.lower())
        self.assertIn("constraint_type = 'check'", migration.lower())
        self.assertLess(
            migration.index("CALL add_learning_material_targeting();"),
            migration.index("DROP PROCEDURE add_learning_material_targeting;"),
        )

    def test_targeting_constraint_contract_preserves_legacy_and_requires_class_for_student(self):
        def constraint_holds(target_class_id, target_student_id):
            return target_student_id is None or target_class_id is not None

        self.assertTrue(constraint_holds(None, None))
        self.assertTrue(constraint_holds(1, None))
        self.assertTrue(constraint_holds(1, 2))
        self.assertFalse(constraint_holds(None, 2))


class FailingAttachmentCursor(fixture.CursorAdapter):
    def execute(self, query, args=()):
        if "INSERT INTO note_attachments" in query:
            raise RuntimeError("simulated attachment metadata failure")
        return super().execute(query, args)


class FailingAttachmentConnection(fixture.ConnectionAdapter):
    def cursor(self):
        return FailingAttachmentCursor(self.connection)


class LearningMaterialApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.QuizStatisticsTests.setUpClass()
        cls.backend = fixture.QuizStatisticsTests.backend

    def setUp(self):
        fixture.QuizStatisticsTests.setUp(self)
        self.upload_directory = tempfile.TemporaryDirectory()
        self.original_upload_root = self.backend.app.config["LEARNING_MATERIAL_UPLOAD_DIR"]
        self.backend.app.config["LEARNING_MATERIAL_UPLOAD_DIR"] = self.upload_directory.name

    def tearDown(self):
        self.backend.app.config["LEARNING_MATERIAL_UPLOAD_DIR"] = self.original_upload_root
        fixture.QuizStatisticsTests.tearDown(self)
        self.upload_directory.cleanup()

    def login(self, user_id=2, role="teacher"):
        with self.client.session_transaction() as session:
            session.clear()
            session.update(user_id=user_id, username=f"user-{user_id}", role=role)

    def assign_teacher(self, teacher_id, class_id, subject_id=1):
        self.db.execute(
            "INSERT INTO teacher_class_subjects VALUES(?,?,?,?,?)",
            (2 + teacher_id + class_id, teacher_id, class_id, subject_id, "2026-01-02"),
        )
        self.db.commit()

    def upload_material(self, *, role_id=2, class_id=1, student_id="", content="Written content", files=()):
        self.login(role_id, "teacher")
        form = {
            "title": "Force lesson",
            "subject": "Science",
            "chapter": "Force",
            "content": content,
            "class_id": str(class_id),
        }
        if student_id != "":
            form["student_id"] = str(student_id)
        if files:
            form["files"] = [
                (io.BytesIO(file_content), filename)
                for filename, file_content in files
            ]
        return self.client.post(
            "/api/teacher/notes", data=form, content_type="multipart/form-data"
        )

    def test_teacher_upload_requires_exact_class_subject_assignment(self):
        self.db.execute("INSERT INTO subjects VALUES(2,'Mathematics','MATH','2026-01-01')")
        self.db.commit()

        allowed = self.upload_material(class_id=1)
        wrong_class = self.upload_material(class_id=2)
        self.assertEqual(allowed.status_code, 201)
        self.assertEqual(wrong_class.status_code, 403)

        self.login(2, "teacher")
        wrong_subject = self.client.post("/api/teacher/notes", json={
            "title": "Math", "subject": "Mathematics", "chapter": "Numbers",
            "content": "Numbers", "class_id": 1,
        })
        self.assertEqual(wrong_subject.status_code, 403)

    def test_options_return_only_current_assigned_classes_and_students(self):
        self.login(2, "teacher")
        response = self.client.get("/api/teacher/notes/options")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["assignments"], [{
            "class_id": 1, "class_name": "Grade 10", "grade": "10",
            "section": "Default", "subject_id": 1, "subject_name": "Science",
        }])
        self.assertEqual(response.json["students"], [{
            "student_id": 1, "full_name": "Student One", "class_id": 1,
        }])
        self.assertNotIn("email", response.json["students"][0])

    def test_specific_student_must_be_currently_enrolled_in_target_class(self):
        response = self.upload_material(class_id=1, student_id=2)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notes").fetchone()[0], 0)

    def test_file_only_and_text_only_materials_are_supported(self):
        text_only = self.upload_material(content="Written lesson")
        file_only = self.upload_material(content="", files=[("lesson.pdf", b"pdf bytes")])
        self.assertEqual(text_only.status_code, 201)
        self.assertEqual(file_only.status_code, 201)

        self.login(2, "teacher")
        empty = self.client.post("/api/teacher/notes", data={
            "title": "Empty", "subject": "Science", "chapter": "Force",
            "content": "", "class_id": "1",
        }, content_type="multipart/form-data")
        self.assertEqual(empty.status_code, 400)

    def test_learning_material_list_and_detail_serialize_note_and_attachment_times(self):
        created = self.upload_material(
            content="Written lesson", files=[("lesson.pdf", b"pdf bytes")]
        )
        note_id = created.json["note_id"]
        self.db.execute(
            "UPDATE notes SET created_at='2026-09-30 00:59:08' WHERE id=?",
            (note_id,),
        )
        self.db.execute(
            "UPDATE note_attachments SET created_at='2026-09-30 00:59:08' WHERE note_id=?",
            (note_id,),
        )
        self.db.commit()

        self.login(2, "teacher")
        teacher_list = self.client.get("/api/teacher/notes")
        listed = teacher_list.json["notes"][0]
        detail = self.client.get(f"/api/teacher/notes/{note_id}").json["note"]
        self.assertEqual(listed["created_at"], "Sep 30, 2026, 12:59 AM NPT")
        self.assertEqual(
            listed["attachments"][0]["created_at"],
            "Sep 30, 2026, 12:59 AM NPT",
        )
        self.assertEqual(detail["created_at"], "Sep 30, 2026, 12:59 AM NPT")
        self.assertEqual(
            detail["attachments"][0]["created_at"],
            "Sep 30, 2026, 12:59 AM NPT",
        )

        self.login(1, "student")
        student_list = self.client.get("/api/student/notes")
        student_material = student_list.json["notes"][0]
        self.assertEqual(
            student_material["created_at"], "Sep 30, 2026, 12:59 AM NPT"
        )
        self.assertEqual(
            student_material["attachments"][0]["created_at"],
            "Sep 30, 2026, 12:59 AM NPT",
        )

    def test_invalid_multipart_file_rejects_entire_material_request(self):
        unsupported = self.upload_material(files=[("image.png", b"image bytes")])
        self.assertEqual(unsupported.status_code, 400)
        self.assertIn("file type", unsupported.json["error"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notes").fetchone()[0], 0)

        mixed_selection = self.upload_material(files=[
            ("lesson.pdf", b"pdf bytes"), ("image.png", b"image bytes"),
        ])
        self.assertEqual(mixed_selection.status_code, 400)
        self.assertIn("file type", mixed_selection.json["error"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notes").fetchone()[0], 0)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM note_attachments").fetchone()[0], 0
        )
        self.assertEqual(list(Path(self.upload_directory.name).iterdir()), [])

    def test_student_specific_material_is_hidden_from_peer_and_download_is_protected(self):
        self.db.execute(
            "UPDATE student_class_enrollments SET ended_at='2026-01-03' WHERE id=2"
        )
        self.db.execute(
            """INSERT INTO student_class_enrollments
               (id,student_id,class_id,academic_year,started_at,ended_at,transfer_note,created_at)
               VALUES(3,2,1,NULL,'2026-01-03',NULL,NULL,'2026-01-03')"""
        )
        self.db.commit()
        created = self.upload_material(
            student_id=1, content="", files=[("../../Force Notes.pdf", b"student A")]
        )
        self.assertEqual(created.status_code, 201)
        note_id = created.json["note_id"]

        self.login(1, "student")
        listing_a = self.client.get("/api/student/notes")
        self.assertEqual([item["id"] for item in listing_a.json["notes"]], [note_id])
        attachment_id = listing_a.json["notes"][0]["attachments"][0]["id"]
        self.assertEqual(listing_a.json["notes"][0]["attachments"][0]["original_filename"], "Force_Notes.pdf")
        download = self.client.get(
            f"/api/student/notes/{note_id}/attachments/{attachment_id}/download"
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, b"student A")
        self.assertIn("attachment;", download.headers["Content-Disposition"].lower())
        download.close()

        self.login(5, "student")
        self.assertEqual(self.client.get("/api/student/notes").json["notes"], [])
        denied = self.client.get(
            f"/api/student/notes/{note_id}/attachments/{attachment_id}/download"
        )
        self.assertEqual(denied.status_code, 404)

    def test_transferred_student_loses_old_class_materials_but_files_remain(self):
        self.assign_teacher(4, 2)
        class_material = self.upload_material(
            class_id=1, content="", files=[("class.pdf", b"class A")]
        )
        specific_material = self.upload_material(
            class_id=1, student_id=1, content="", files=[("student.docx", b"student A")]
        )
        self.assertEqual(class_material.status_code, 201)
        self.assertEqual(specific_material.status_code, 201)
        self.db.execute(
            "UPDATE student_class_enrollments SET ended_at='2026-02-01' WHERE student_id=1 AND ended_at IS NULL"
        )
        self.db.execute(
            """INSERT INTO student_class_enrollments
               (id,student_id,class_id,academic_year,started_at,ended_at,transfer_note,created_at)
               VALUES(3,1,2,NULL,'2026-02-01',NULL,NULL,'2026-02-01')"""
        )
        self.db.commit()
        class_b = self.upload_material(
            role_id=4, class_id=2, content="", files=[("class-b.pptx", b"class B")]
        )
        self.assertEqual(class_b.status_code, 201)

        self.login(1, "student")
        materials = self.client.get("/api/student/notes").json["notes"]
        self.assertEqual([item["id"] for item in materials], [class_b.json["note_id"]])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notes").fetchone()[0], 3)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM note_attachments").fetchone()[0], 3)
        for old_id in (class_material.json["note_id"], specific_material.json["note_id"]):
            self.assertEqual(self.client.get(
                f"/api/student/notes/{old_id}/attachments/1/download"
            ).status_code, 404)

    def test_legacy_null_target_note_remains_visible_by_current_subject(self):
        self.db.execute(
            """INSERT INTO notes
               (id,title,subject,chapter,content,created_at,uploaded_by)
               VALUES(1,'Legacy','Science','Force','Old content','2026-01-01',2)"""
        )
        self.db.commit()
        self.login(1, "student")
        response = self.client.get("/api/student/notes")
        self.assertEqual([item["title"] for item in response.json["notes"]], ["Legacy"])
        legacy_targeting = self.db.execute(
            "SELECT target_class_id, target_student_id FROM notes WHERE id=1"
        ).fetchone()
        self.assertIsNone(legacy_targeting["target_class_id"])
        self.assertIsNone(legacy_targeting["target_student_id"])

    def test_dashboard_and_recommendation_resources_exclude_peer_targeted_material(self):
        self.db.execute(
            "UPDATE student_class_enrollments SET ended_at='2026-01-03' WHERE id=2"
        )
        self.db.execute(
            """INSERT INTO student_class_enrollments
               (id,student_id,class_id,academic_year,started_at,ended_at,transfer_note,created_at)
               VALUES(3,2,1,NULL,'2026-01-03',NULL,NULL,'2026-01-03')"""
        )
        self.db.commit()
        created = self.upload_material(
            student_id=1, content="Student specific resource"
        )
        self.assertEqual(created.status_code, 201)

        self.login(5, "student")
        dashboard = self.client.get("/api/student/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json["stats"]["available_notes"], 0)

        cursor = self.backend.mysql.connection.cursor()
        try:
            peer_notes, _ = self.backend.fetch_learning_recommendation_resources(
                cursor, 1, {"science"}, 2
            )
            owner_notes, _ = self.backend.fetch_learning_recommendation_resources(
                cursor, 1, {"science"}, 1
            )
        finally:
            cursor.close()
        self.assertEqual(peer_notes, [])
        self.assertEqual([item["id"] for item in owner_notes], [created.json["note_id"]])

    def test_teacher_can_edit_add_download_and_remove_own_attachment(self):
        created = self.upload_material(content="Original content")
        note_id = created.json["note_id"]
        self.login(2, "teacher")
        updated = self.client.put(f"/api/teacher/notes/{note_id}", json={
            "title": "Updated", "subject": "Science", "chapter": "Motion",
            "content": "Updated content", "class_id": 1,
        })
        self.assertEqual(updated.status_code, 200)
        added = self.client.post(
            f"/api/teacher/notes/{note_id}/attachments",
            data={"files": [(io.BytesIO(b"teacher verification"), "verify.pptx")]},
            content_type="multipart/form-data",
        )
        self.assertEqual(added.status_code, 201)
        detail = self.client.get(f"/api/teacher/notes/{note_id}").json["note"]
        self.assertEqual(detail["target_class_id"], 1)
        self.assertEqual(detail["attachments"][0]["original_filename"], "verify.pptx")
        self.assertNotIn("stored_filename", detail["attachments"][0])
        attachment_id = detail["attachments"][0]["id"]
        downloaded = self.client.get(
            f"/api/teacher/notes/{note_id}/attachments/{attachment_id}/download"
        )
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.data, b"teacher verification")
        downloaded.close()
        removed = self.client.delete(
            f"/api/teacher/notes/{note_id}/attachments/{attachment_id}"
        )
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM note_attachments WHERE note_id=?", (note_id,)
        ).fetchone()[0], 0)

        self.login(4, "teacher")
        self.assertEqual(self.client.get(
            f"/api/teacher/notes/{note_id}/attachments/{attachment_id}/download"
        ).status_code, 404)

    def test_teacher_cannot_retarget_to_unassigned_class_subject(self):
        created = self.upload_material(content="Original content")
        note_id = created.json["note_id"]
        self.login(2, "teacher")
        response = self.client.put(f"/api/teacher/notes/{note_id}", json={
            "title": "Changed", "subject": "Science", "chapter": "Force",
            "content": "Changed", "class_id": 2,
        })
        self.assertEqual(response.status_code, 403)
        stored = self.db.execute(
            "SELECT target_class_id FROM notes WHERE id=?", (note_id,)
        ).fetchone()
        self.assertEqual(stored["target_class_id"], 1)

    def test_cannot_remove_final_attachment_from_empty_material(self):
        created = self.upload_material(
            content="", files=[("only.pdf", b"only content")]
        )
        note_id = created.json["note_id"]
        self.login(2, "teacher")
        attachment = self.client.get(f"/api/teacher/notes/{note_id}").json["note"]["attachments"][0]
        response = self.client.delete(
            f"/api/teacher/notes/{note_id}/attachments/{attachment['id']}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM note_attachments WHERE note_id=?", (note_id,)
        ).fetchone()[0], 1)

    def test_deleting_material_removes_its_attachment_metadata_and_file(self):
        created = self.upload_material(
            content="With file", files=[("delete.pdf", b"delete me")]
        )
        note_id = created.json["note_id"]
        stored_filename = self.db.execute(
            "SELECT stored_filename FROM note_attachments WHERE note_id=?", (note_id,)
        ).fetchone()[0]
        stored_path = safe_storage_path(self.upload_directory.name, stored_filename)
        self.assertTrue(stored_path.exists())
        self.login(2, "teacher")
        response = self.client.delete(f"/api/teacher/notes/{note_id}")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(stored_path.exists())
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM note_attachments WHERE note_id=?", (note_id,)
        ).fetchone()[0], 0)

    def test_attachment_id_cannot_be_mixed_with_another_note(self):
        note_a = self.upload_material(content="A", files=[("a.pdf", b"a")])
        note_b = self.upload_material(content="B", files=[("b.pdf", b"b")])
        self.login(1, "student")
        attachments = self.client.get("/api/student/notes").json["notes"]
        by_note = {item["id"]: item["attachments"][0]["id"] for item in attachments}
        mixed = self.client.get(
            f"/api/student/notes/{note_a.json['note_id']}/attachments/{by_note[note_b.json['note_id']]}/download"
        )
        self.assertEqual(mixed.status_code, 404)

    def test_database_failure_rolls_back_note_and_removes_written_file(self):
        self.login(2, "teacher")
        original_connection = self.backend.mysql.connection
        self.backend.mysql.connection = FailingAttachmentConnection(self.db)
        try:
            response = self.client.post("/api/teacher/notes", data={
                "title": "Will roll back", "subject": "Science", "chapter": "Force",
                "content": "", "class_id": "1",
                "files": [(io.BytesIO(b"must be removed"), "rollback.pdf")],
            }, content_type="multipart/form-data")
        finally:
            self.backend.mysql.connection = original_connection
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notes").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM note_attachments").fetchone()[0], 0)
        self.assertEqual(list(Path(self.upload_directory.name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()