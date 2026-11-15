# Copyright (c) 2026, Himguru and contributors
# For license information, please see license.txt

"""Populate ``Program.courses`` from legacy programme-course data.

Runs after model sync, which recreates the ``Program Course`` child table with
the restored DocType and its new columns. The patch is intentionally additive:

* legacy ``tabProgram Course`` rows are normalised in place (parent metadata,
  missing defaults) rather than rewritten or deleted;
* courses linked through the transitional ``Course.program`` field are appended
  when the programme has no equivalent child row;
* ``Course.program`` is never cleared or changed.

Re-running the patch is safe: existing ``(program, course)`` pairs are skipped.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint, now

PROGRAM_COURSE_DOCTYPE = "Program Course"


def execute():
	if not frappe.db.table_exists(PROGRAM_COURSE_DOCTYPE):
		return {"normalised": 0, "created": 0}

	if not frappe.get_meta("Program").has_field("courses"):
		return {"normalised": 0, "created": 0}

	columns = _table_columns()
	normalised = _normalise_legacy_rows(columns)
	created = _populate_missing_courses(columns)

	frappe.logger("education").info(
		"Program Course compatibility migration: normalised %s rows, created %s rows",
		normalised,
		created,
	)
	return {"normalised": normalised, "created": created}


def _table_columns() -> set[str]:
	return {row[0] for row in frappe.db.sql("desc `tabProgram Course`")}


def _normalise_legacy_rows(columns: set[str]) -> int:
	"""Fill missing child-table metadata without changing course assignments."""
	fields = ["name", "parent", "parenttype", "parentfield", "idx", "course", "course_name"]
	for fieldname in ("required", "sort_order", "is_active"):
		if fieldname in columns:
			fields.append(fieldname)

	rows = frappe.get_all(
		PROGRAM_COURSE_DOCTYPE,
		fields=fields,
		order_by="idx asc",
	)

	normalised = 0
	for row in rows:
		if not row.get("name") or not row.get("parent") or not row.get("course"):
			continue

		if not _is_program_course_row(row):
			continue

		if not frappe.db.exists("Program", row.parent):
			# Leave orphaned legacy rows untouched. They are not readable through Program.
			continue

		updates = {}
		if row.get("parenttype") != "Program":
			updates["parenttype"] = "Program"
		if row.get("parentfield") != "courses":
			updates["parentfield"] = "courses"

		if not row.get("course_name"):
			course_name = frappe.db.get_value("Course", row.course, "course_name")
			if course_name:
				updates["course_name"] = course_name

		if "required" in columns and row.get("required") is None:
			updates["required"] = 1
		if "is_active" in columns and row.get("is_active") is None:
			updates["is_active"] = 1
		if "sort_order" in columns and not cint(row.get("sort_order")):
			updates["sort_order"] = cint(row.get("idx"))

		if updates:
			frappe.db.set_value(
				PROGRAM_COURSE_DOCTYPE,
				row.name,
				updates,
				update_modified=False,
			)
			normalised += 1

	return normalised


def _populate_missing_courses(columns: set[str]) -> int:
	"""Append courses from ``Course.program`` that the programme does not have yet."""
	if not frappe.db.has_column("Course", "program"):
		return 0

	existing = set()
	for row in frappe.get_all(
		PROGRAM_COURSE_DOCTYPE,
		fields=["parent", "parenttype", "parentfield", "course"],
	):
		if _is_program_course_row(row) and row.get("parent") and row.get("course"):
			existing.add((row.parent, row.course))

	max_idx = {
		row.parent: cint(row.max_idx)
		for row in frappe.db.sql(
			"select parent, coalesce(max(idx), 0) as max_idx from `tabProgram Course` group by parent",
			as_dict=True,
		)
	}

	created = 0
	for program in frappe.get_all("Program", pluck="name"):
		courses = frappe.get_all(
			"Course",
			filters={"program": program},
			fields=["name", "course_name"],
			order_by="course_name asc",
		)
		for course in courses:
			key = (program, course.name)
			if key in existing:
				continue

			max_idx[program] = max_idx.get(program, 0) + 1
			_insert_row(
				columns=columns,
				program=program,
				idx=max_idx[program],
				course=course.name,
				course_name=course.course_name,
			)
			existing.add(key)
			created += 1

	return created


def _insert_row(columns: set[str], program: str, idx: int, course: str, course_name: str | None) -> None:
	"""Insert a child row directly so parent validation cannot rewrite legacy data."""
	user = frappe.session.user or "Administrator"
	timestamp = now()
	payload = {
		"name": frappe.generate_hash(length=10),
		"owner": user,
		"modified_by": user,
		"creation": timestamp,
		"modified": timestamp,
		"docstatus": 0,
		"idx": idx,
		"parent": program,
		"parentfield": "courses",
		"parenttype": "Program",
		"course": course,
		"course_name": course_name,
		"required": 1,
		"is_active": 1,
		"sort_order": idx,
		"weekly_periods": 0,
	}

	fieldnames = [fieldname for fieldname in payload if fieldname in columns]
	values = [payload[fieldname] for fieldname in fieldnames]
	placeholders = ", ".join(["%s"] * len(fieldnames))
	column_names = ", ".join(f"`{fieldname}`" for fieldname in fieldnames)
	frappe.db.sql(
		f"insert into `tabProgram Course` ({column_names}) values ({placeholders})",
		values,
	)


def _is_program_course_row(row) -> bool:
	"""Accept legacy rows whose parenttype/parentfield were not populated."""
	parenttype = row.get("parenttype") or "Program"
	parentfield = row.get("parentfield") or "courses"
	return parenttype == "Program" and parentfield == "courses"
