from unittest import mock
import pytest
import db_adapter


class Cursor:
    def __init__(self, results):
        self.results = iter(results)
        self.sql = []
    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        assert sql.lstrip().upper().startswith("SELECT")
        self.current = next(self.results)
    def fetchone(self): return self.current
    def fetchall(self): return self.current
    def close(self): pass


@pytest.fixture
def real(monkeypatch):
    monkeypatch.setenv("VOXERP_USE_REAL_DB", "True")
    def connection(results):
        cursor = Cursor(results)
        conn = mock.Mock()
        conn.cursor.return_value = cursor
        monkeypatch.setattr(db_adapter, "_get_connection", lambda: conn)
        return conn, cursor
    return connection


def test_consolidated_marks_mapping(real):
    conn, cursor = real([(917, "reg"), [(1, "2026-01-01", 5, "IT25201", "Course", "IAT1,IAT2", "100,100", "62,77", None, None, None, None, None, None)]])
    result = db_adapter.get_marks(917, "IT25201")
    assert result["status"] == "ok"
    assert [r["marks_obtained"] for r in result["rows"]] == [62, 77]
    assert [r["percentage"] for r in result["rows"]] == [62, 77]
    assert "examination_management_overallconsolidaterecord" in cursor.sql[1][0]
    assert "SUM(" not in cursor.sql[1][0]
    conn.close.assert_called_once()


def test_hourly_and_daily_separate(real):
    conn, cursor = real([(917,), [(1, "2026-01-01", "present", None, None, None, "IT25201", "Course", 1)]])
    result = db_adapter.get_attendance(917, "it-25201")
    assert result["status"] == "ok"
    assert result["rows"][0]["period"] == 1
    assert "student_management_hourattendance" in cursor.sql[1][0]
    conn, cursor = real([(917,), []])
    assert db_adapter.get_attendance(917)["status"] == "no_data"
    assert "student_management_daily_attendance" in cursor.sql[1][0]
    assert "course_id" not in cursor.sql[1][0]


def test_all_timetable_periods_and_empty_slots(real):
    allocation = (1, "Monday", "A", 2, 3, "C1", None, "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10")
    courses = [(i, "C" + str(i), "Course " + str(i)) for i in range(1, 11) if i != 2]
    conn, cursor = real([(2, 3, "A"), [allocation], *courses])
    result = db_adapter.get_timetable(917)
    assert [r["period"] for r in result["rows"]] == ["period_" + str(i) for i in range(1, 11) if i != 2]
    assert cursor.sql[1][1] == (2, 3, "A")
    assert "nineth_period" in cursor.sql[1][0]
    assert cursor.sql[2][1] == ("C1",)
    conn.close.assert_called_once()


def test_disabled_adapter_write_issues_only_selects(real):
    conn, cursor = real([(917,), (5, "IT25201", "Course")])
    assert db_adapter.mark_attendance(917, "IT25201", "2026-01-01", "absent", "actor", period=1)["status"] == "disabled"
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


@pytest.mark.parametrize("date,status", [("2026-02-30", "present"), ("01-01-2026", "present"), ("2026-01-01", "invalid")])
def test_invalid_write_input_before_connection(real,date,status):
    conn, cursor = real([])
    assert db_adapter.mark_attendance(917, "IT25201", date, status, "actor", period=1)["status"] == "invalid"
    conn.cursor.assert_not_called()
