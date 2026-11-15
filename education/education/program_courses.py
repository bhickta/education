# Copyright (c) 2026, Himguru and contributors
# For license information, please see license.txt

"""Read programme curriculum with compatibility for pre-Program-Course sites.

Phase 2 restores ``Program.courses`` (the ``Program Course`` child table) as the
curriculum source. Older sites may still have data in one of two places:

* legacy ``tabProgram Course`` rows (the same child table, before it was retired), or
* ``Course.program``, the single-programme link introduced while the child table
  was absent.

Reads prefer the child table, then fall back to ``Course.program``. Nothing here
writes data; the migration patch owns backfilling.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

PROGRAM_COURSE_DOCTYPE = "Program Course"
PROGRAM_COURSE_FIELDS = (
	"course",
	"course_name",
	"category",
	"required",
	"sort_order",
	"weekly_periods",
	"grade_template",
	"is_active",
)


def is_multi_company() -> bool:
	"""Return True when the site is configured for more than one Company.

	Company consistency on programme courses is only meaningful on multi-company
	sites; single-company installs cannot have a real mismatch.
	"""
	try:
		return cint(frappe.db.count("Company")) > 1
	except Exception:
		return False


def get_program_course_rows(program_name: str, include_inactive: bool = False) -> list[frappe._dict]:
	"""Return normalised curriculum rows for a programme.

	The result prefers ``Program.courses`` rows. If the programme has no child
	rows at all, it falls back to ``Course.program`` so existing sites keep
	working before the migration patch has run.
	"""
	if not program_name:
		return []

	rows = _get_program_course_table_rows(program_name)
	if rows:
		rows = _normalise_rows(rows)
		if not include_inactive:
			rows = [row for row in rows if row.is_active]
		return _dedupe_rows(rows)

	return _get_course_program_rows(program_name)


def get_program_course_names(program_name: str, include_inactive: bool = False) -> list[str]:
	"""Return course names for a programme, preserving curriculum order."""
	names = []
	seen = set()
	for row in get_program_course_rows(program_name, include_inactive=include_inactive):
		if not row.course or row.course in seen:
			continue
		seen.add(row.course)
		names.append(row.course)
	return names


def get_programs_for_course(course: str) -> list[str]:
	"""Return every programme linked to a course through either compatibility path."""
	if not course:
		return []

	programs = []

	def add(program):
		if program and program not in programs and frappe.db.exists("Program", program):
			programs.append(program)

	if frappe.db.has_column("Course", "program"):
		add(frappe.db.get_value("Course", course, "program"))

	if _program_course_table_exists():
		for row in frappe.get_all(
			PROGRAM_COURSE_DOCTYPE,
			filters={"course": course},
			fields=["parent", "parenttype", "parentfield"],
		):
			if _is_program_course_row(row):
				add(row.parent)

	return programs


def get_program_for_course(course: str) -> str | None:
	"""Return the programme a course belongs to when it is unambiguous.

	``Course.program`` stays authoritative while it exists. The child table is
	only used as a compatibility fallback when the legacy link is empty and the
	course appears in exactly one programme.
	"""
	programs = get_programs_for_course(course)
	if len(programs) == 1:
		return programs[0]
	return None


def _program_course_table_exists() -> bool:
	try:
		return bool(frappe.db.table_exists(PROGRAM_COURSE_DOCTYPE))
	except Exception:
		return False


def _get_program_course_table_rows(program_name: str) -> list[frappe._dict]:
	if not _program_course_table_exists():
		return []

	fields = ["name", "parent", "parenttype", "parentfield", "idx", "course", "course_name"]
	for fieldname in PROGRAM_COURSE_FIELDS:
		if fieldname in fields:
			continue
		if frappe.db.has_column(PROGRAM_COURSE_DOCTYPE, fieldname):
			fields.append(fieldname)

	rows = frappe.get_all(
		PROGRAM_COURSE_DOCTYPE,
		filters={"parent": program_name},
		fields=fields,
		order_by="idx asc",
	)
	return [row for row in rows if _is_program_course_row(row)]


def _is_program_course_row(row) -> bool:
	"""Accept legacy rows whose parenttype/parentfield were not populated."""
	parenttype = row.get("parenttype") or "Program"
	parentfield = row.get("parentfield") or "courses"
	return parenttype == "Program" and parentfield == "courses"


def _get_course_program_rows(program_name: str) -> list[frappe._dict]:
	if not frappe.db.has_column("Course", "program"):
		return []

	courses = frappe.get_all(
		"Course",
		filters={"program": program_name},
		fields=["name", "course_name"],
		order_by="course_name asc",
	)
	rows = []
	for idx, course in enumerate(courses, start=1):
		rows.append(
			frappe._dict(
				name=None,
				parent=program_name,
				parenttype="Program",
				parentfield="courses",
				idx=idx,
				course=course.name,
				course_name=course.course_name,
				category=None,
				required=1,
				sort_order=idx,
				weekly_periods=0,
				grade_template=None,
				is_active=1,
				source="course.program",
			)
		)
	return rows


def _normalise_rows(rows) -> list[frappe._dict]:
	course_names = [row.course for row in rows if row.get("course")]
	names = {}
	if course_names:
		names = {
			course.name: course.course_name
			for course in frappe.get_all(
				"Course",
				filters={"name": ("in", course_names)},
				fields=["name", "course_name"],
			)
		}

	normalised = []
	for idx, row in enumerate(rows, start=1):
		course = row.get("course")
		if not course:
			continue

		row_idx = cint(row.get("idx")) or idx
		sort_order = row.get("sort_order")
		is_active = row.get("is_active")

		normalised.append(
			frappe._dict(
				name=row.get("name"),
				parent=row.get("parent"),
				parenttype="Program",
				parentfield="courses",
				idx=row_idx,
				course=course,
				course_name=row.get("course_name") or names.get(course),
				category=row.get("category"),
				required=1 if row.get("required") is None else cint(row.get("required")),
				sort_order=row_idx if sort_order is None else cint(sort_order),
				weekly_periods=0 if row.get("weekly_periods") is None else cint(row.get("weekly_periods")),
				grade_template=row.get("grade_template"),
				is_active=1 if is_active is None else cint(is_active),
				source="program_course",
			)
		)

	normalised.sort(key=lambda row: (cint(row.sort_order), cint(row.idx)))
	return normalised


def _dedupe_rows(rows) -> list[frappe._dict]:
	"""Return the first row for each course; duplicates are invalid input, not data."""
	seen = set()
	unique = []
	for row in rows:
		if not row.course or row.course in seen:
			continue
		seen.add(row.course)
		unique.append(row)
	return unique
