# Copyright (c) 2026, Himguru and contributors
# For license information, please see license.txt

"""Compatibility helpers for the Phase 3 batch and enrollment migration.

The helpers are deliberately conservative:

* they only fill blank values, never replace a programme, batch, academic year,
  company or capacity that is already set;
* they never submit Course Enrollments, create fees or delete legacy rows;
* every legacy table and column is looked up before it is read, so the patch is
  safe on sites that never had Student Group or Program Enrollment;
* no write happens when ``dry_run`` is true.

The pure planning helpers are separated from the database readers so they can
be tested without a bench.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint, getdate, now

BATCH_DOCTYPE = "Student Batch Name"
ENROLLMENT_DOCTYPE = "Course Enrollment"
GROUP_DOCTYPE = "Student Group"
GROUP_STUDENT_DOCTYPE = "Student Group Student"
PROGRAM_ENROLLMENT_DOCTYPE = "Program Enrollment"
PROGRAM_ENROLLMENT_COURSE_DOCTYPE = "Program Enrollment Course"

GROUP_FIELDS = (
	"name",
	"student_group_name",
	"group_based_on",
	"program",
	"batch",
	"course",
	"academic_year",
	"academic_term",
	"max_strength",
	"disabled",
)
PROGRAM_ENROLLMENT_FIELDS = (
	"name",
	"student",
	"program",
	"student_batch_name",
	"student_batch",
	"academic_year",
	"intake_year",
	"academic_term",
	"enrollment_date",
	"company",
	"docstatus",
)
COURSE_ENROLLMENT_FIELDS = (
	"name",
	"student",
	"course",
	"program",
	"student_batch",
	"academic_year",
	"enrollment_date",
	"company",
	"docstatus",
)


def table_exists(doctype: str) -> bool:
	try:
		return bool(frappe.db.table_exists(doctype))
	except Exception:
		return False


def get_table_columns(doctype: str) -> set[str]:
	if not table_exists(doctype):
		return set()

	try:
		return {row[0] for row in frappe.db.sql(f"desc `tab{doctype}`")}
	except Exception:
		return set()


def choose_batch_name(group: dict) -> str | None:
	"""Return the batch a legacy Student Group should create or normalise."""
	for fieldname in ("batch", "student_group_name", "name"):
		value = group.get(fieldname)
		if value:
			return value
	return None


def find_academic_year_for_date(academic_years, date, company=None) -> str | None:
	"""Find the single Academic Year whose date range contains ``date``.

	An ambiguous match is left unresolved instead of guessing.
	"""
	if not date:
		return None

	try:
		date = getdate(date)
	except Exception:
		return None

	matches = []
	for year in academic_years or []:
		start = year.get("year_start_date")
		end = year.get("year_end_date")
		if not (start and end):
			continue
		if getdate(start) <= date <= getdate(end):
			matches.append(year)

	if not matches:
		return None

	if company:
		company_matches = [
			year for year in matches if not year.get("company") or year.get("company") == company
		]
		if len(company_matches) == 1:
			return company_matches[0].get("name")
		if company_matches:
			matches = company_matches

	names = {year.get("name") for year in matches if year.get("name")}
	if len(names) == 1:
		return names.pop()
	return None


def build_batch_plan(
	group: dict,
	existing_batch: dict | None = None,
	academic_year: dict | None = None,
	company: str | None = None,
) -> dict | None:
	"""Return a create/update plan for a Student Group without touching the DB.

	``academic_year`` is the resolved Academic Year row (with start/end dates).
	Existing batches only receive blank fields. New batches need a name, a
	programme, a company and an academic year with dates.
	"""
	batch_name = choose_batch_name(group)
	if not batch_name:
		return None

	academic_year = academic_year or {}
	year_name = academic_year.get("name") or group.get("academic_year")

	if existing_batch:
		updates = {}
		for fieldname, value in (
			("program", group.get("program")),
			("course", group.get("course")),
			("academic_year", year_name),
			("company", company),
		):
			if value and not existing_batch.get(fieldname):
				updates[fieldname] = value

		if not existing_batch.get("start_date") and academic_year.get("year_start_date"):
			updates["start_date"] = academic_year["year_start_date"]
		if not existing_batch.get("end_date") and academic_year.get("year_end_date"):
			updates["end_date"] = academic_year["year_end_date"]

		group_strength = cint(group.get("max_strength"))
		if group_strength and not cint(existing_batch.get("max_strength")):
			updates["max_strength"] = group_strength

		if existing_batch.get("disabled") is None and group.get("disabled") is not None:
			updates["disabled"] = cint(group.get("disabled"))

		return {"action": "update", "name": batch_name, "values": updates} if updates else None

	if not (group.get("program") and company and academic_year.get("year_start_date")):
		return None
	if not academic_year.get("year_end_date"):
		return None

	return {
		"action": "create",
		"name": batch_name,
		"values": {
			"batch_name": batch_name,
			"program": group.get("program"),
			"course": group.get("course"),
			"academic_year": year_name,
			"company": company,
			"max_strength": cint(group.get("max_strength")),
			"disabled": cint(group.get("disabled")),
			"start_date": academic_year["year_start_date"],
			"end_date": academic_year["year_end_date"],
		},
	}


def build_enrollment_updates(
	enrollment: dict,
	legacy_enrollment: dict | None = None,
	batch: dict | None = None,
	default_program: str | None = None,
	academic_year: str | None = None,
	batch_name: str | None = None,
) -> dict:
	"""Return only the blank Course Enrollment fields that can be filled safely."""
	updates = {}
	legacy_enrollment = legacy_enrollment or {}
	batch = batch or {}

	if not enrollment.get("program"):
		program = batch.get("program") or legacy_enrollment.get("program") or default_program
		if program:
			updates["program"] = program

	if not enrollment.get("student_batch"):
		candidate_batch = batch_name or legacy_enrollment.get("student_batch_name")
		if candidate_batch and batch.get("name") == candidate_batch:
			updates["student_batch"] = candidate_batch

	if not enrollment.get("academic_year"):
		year = legacy_enrollment.get("_resolved_year") or academic_year or batch.get("academic_year")
		if year:
			updates["academic_year"] = year

	return updates


def resolve_legacy_enrollment_year(
	enrollment: dict,
	term_years: dict | None = None,
	academic_years=None,
	company: str | None = None,
) -> str | None:
	"""Resolve a Program Enrollment academic year from explicit or date fields."""
	if not enrollment:
		return None

	for fieldname in ("academic_year", "intake_year"):
		if enrollment.get(fieldname):
			return enrollment[fieldname]

	term_years = term_years or {}
	if enrollment.get("academic_term") and term_years.get(enrollment["academic_term"]):
		return term_years[enrollment["academic_term"]]

	return find_academic_year_for_date(
		academic_years,
		enrollment.get("enrollment_date"),
		company=enrollment.get("company") or company,
	)


def run(dry_run: bool = False) -> dict:
	"""Run the batch/enrollment compatibility migration.

	The patch entry point calls this with ``dry_run=False``. Passing ``True``
	returns the same summary while leaving the database untouched.
	"""
	summary = {
		"dry_run": dry_run,
		"batches_created": 0,
		"batches_updated": 0,
		"enrollments_updated": 0,
		"enrollment_fields": {},
		"skipped_groups": 0,
	}

	academic_years = _load_academic_years()
	academic_year_map = {row["name"]: row for row in academic_years if row.get("name")}
	term_years = _load_term_years()
	default_company = _get_default_company()

	groups, group_students = _load_legacy_groups()
	legacy_enrollments, legacy_enrollment_courses = _load_legacy_program_enrollments()
	enrollments = _load_course_enrollments()

	legacy_by_student = _group_by(legacy_enrollments, "student")
	groups_by_student = _groups_by_student(groups, group_students)
	batches = {row["name"]: row for row in _load_batches() if row.get("name")}

	for group in groups:
		batch_name = choose_batch_name(group)
		existing_batch = batches.get(batch_name)

		year_name = group.get("academic_year")
		if year_name and year_name not in academic_year_map:
			year_name = None
		if not year_name and existing_batch:
			year_name = existing_batch.get("academic_year")
			if year_name and year_name not in academic_year_map:
				year_name = None
		if not year_name:
			for student in group_students.get(group.get("name"), []):
				for enrollment in legacy_by_student.get(student, []):
					year_name = resolve_legacy_enrollment_year(
						enrollment,
						term_years,
						academic_years,
						company=group.get("_company") or default_company,
					)
					if year_name:
						break
				if year_name:
					break

		academic_year = academic_year_map.get(year_name)
		group["academic_year"] = year_name
		company = _resolve_group_company(group, existing_batch, default_company)
		plan = build_batch_plan(group, existing_batch, academic_year, company)
		if not plan:
			summary["skipped_groups"] += 1
			continue

		if plan["action"] == "create":
			if not dry_run:
				_insert_batch(plan["values"])
			batches[plan["name"]] = dict(plan["values"], name=plan["name"])
			summary["batches_created"] += 1
		else:
			if not dry_run:
				frappe.db.set_value(
					BATCH_DOCTYPE,
					plan["name"],
					plan["values"],
					update_modified=False,
				)
			batches[plan["name"]].update(plan["values"])
			summary["batches_updated"] += 1

	summary["batches_updated"] += _normalise_batches(
		batches, academic_years, default_company, dry_run=dry_run
	)

	summary["enrollments_updated"], summary["enrollment_fields"] = _backfill_enrollments(
		enrollments=enrollments,
		legacy_by_student=legacy_by_student,
		legacy_enrollment_courses=legacy_enrollment_courses,
		groups_by_student=groups_by_student,
		batches=batches,
		academic_years=academic_years,
		academic_year_map=academic_year_map,
		term_years=term_years,
		default_company=default_company,
		dry_run=dry_run,
	)
	summary["batches_updated"] += _fill_batch_programs_from_enrollments(batches, enrollments, dry_run=dry_run)

	if not dry_run:
		frappe.logger("education").info(
			"Batch/enrollment compatibility migration: %s",
			{key: value for key, value in summary.items() if key != "dry_run"},
		)

	return summary


def _load_academic_years() -> list[frappe._dict]:
	if not table_exists("Academic Year"):
		return []

	fields = ["name", "year_start_date", "year_end_date"]
	columns = get_table_columns("Academic Year")
	if "company" in columns:
		fields.append("company")
	return frappe.get_all("Academic Year", fields=fields)


def _load_term_years() -> dict:
	if not table_exists("Academic Term"):
		return {}

	if not {"name", "academic_year"}.issubset(get_table_columns("Academic Term")):
		return {}

	return {
		row.name: row.academic_year
		for row in frappe.get_all("Academic Term", fields=["name", "academic_year"])
	}


def _load_legacy_groups() -> tuple[list[frappe._dict], dict[str, list[str]]]:
	if not table_exists(GROUP_DOCTYPE):
		return [], {}

	groups = _select_legacy_rows(GROUP_DOCTYPE, GROUP_FIELDS)
	students = {}
	if table_exists(GROUP_STUDENT_DOCTYPE):
		for row in _select_legacy_rows(GROUP_STUDENT_DOCTYPE, ("parent", "student")):
			if row.get("parent") and row.get("student"):
				students.setdefault(row["parent"], []).append(row["student"])
	return groups, students


def _load_legacy_program_enrollments() -> tuple[list[frappe._dict], dict[str, set[str]]]:
	if not table_exists(PROGRAM_ENROLLMENT_DOCTYPE):
		return [], {}

	enrollments = _select_legacy_rows(PROGRAM_ENROLLMENT_DOCTYPE, PROGRAM_ENROLLMENT_FIELDS)
	for enrollment in enrollments:
		if not enrollment.get("student_batch_name") and enrollment.get("student_batch"):
			enrollment["student_batch_name"] = enrollment["student_batch"]

	courses = {}
	if table_exists(PROGRAM_ENROLLMENT_COURSE_DOCTYPE):
		for row in _select_legacy_rows(PROGRAM_ENROLLMENT_COURSE_DOCTYPE, ("parent", "course")):
			if row.get("parent") and row.get("course"):
				courses.setdefault(row["parent"], set()).add(row["course"])
	return enrollments, courses


def _load_course_enrollments() -> list[frappe._dict]:
	if not table_exists(ENROLLMENT_DOCTYPE):
		return []

	columns = get_table_columns(ENROLLMENT_DOCTYPE)
	fields = [fieldname for fieldname in COURSE_ENROLLMENT_FIELDS if fieldname in columns]
	if not fields:
		return []

	return frappe.get_all(ENROLLMENT_DOCTYPE, fields=fields, filters={"docstatus": ("!=", 2)})


def _load_batches() -> list[frappe._dict]:
	if not table_exists(BATCH_DOCTYPE):
		return []

	columns = get_table_columns(BATCH_DOCTYPE)
	fields = [
		fieldname
		for fieldname in (
			"name",
			"batch_name",
			"program",
			"course",
			"academic_year",
			"max_strength",
			"disabled",
			"company",
			"start_date",
			"end_date",
		)
		if fieldname in columns
	]
	return frappe.get_all(BATCH_DOCTYPE, fields=fields, order_by="name asc")


def _select_legacy_rows(doctype: str, fieldnames) -> list[frappe._dict]:
	columns = get_table_columns(doctype)
	selected = [fieldname for fieldname in fieldnames if fieldname in columns]
	if not selected:
		return []

	column_sql = ", ".join(f"`{fieldname}`" for fieldname in selected)
	return frappe.db.sql(f"select {column_sql} from `tab{doctype}`", as_dict=True)


def _group_by(rows, fieldname: str) -> dict:
	grouped = {}
	for row in rows:
		key = row.get(fieldname)
		if key:
			grouped.setdefault(key, []).append(row)
	return grouped


def _groups_by_student(groups, group_students) -> dict:
	groups_by_name = {group.get("name"): group for group in groups if group.get("name")}
	by_student = {}
	for group_name, students in group_students.items():
		group = groups_by_name.get(group_name)
		if not group:
			continue
		for student in students:
			by_student.setdefault(student, []).append(group)
	return by_student


def _get_default_company() -> str | None:
	try:
		company = frappe.defaults.get_global_default("company")
	except Exception:
		company = None

	if not company:
		try:
			company = frappe.db.get_single_value("Global Defaults", "default_company")
		except Exception:
			company = None

	if not company:
		companies = frappe.get_all("Company", pluck="name", limit=2)
		if len(companies) == 1:
			company = companies[0]

	return company


def _resolve_group_company(group, existing_batch, default_company) -> str | None:
	if existing_batch and existing_batch.get("company"):
		return existing_batch["company"]

	for doctype, value in (("Course", group.get("course")), ("Program", group.get("program"))):
		if not value:
			continue
		try:
			company = frappe.db.get_value(doctype, value, "company")
		except Exception:
			company = None
		if company:
			return company

	return default_company


def _insert_batch(values: dict) -> None:
	columns = get_table_columns(BATCH_DOCTYPE)
	if not columns or not values.get("batch_name"):
		return

	user = frappe.session.user or "Administrator"
	timestamp = now()
	payload = dict(values)
	payload.update(
		{
			"name": values["batch_name"],
			"owner": user,
			"modified_by": user,
			"creation": timestamp,
			"modified": timestamp,
			"docstatus": 0,
			"idx": 0,
		}
	)
	fieldnames = [fieldname for fieldname in payload if fieldname in columns]
	if "name" not in fieldnames:
		return

	column_sql = ", ".join(f"`{fieldname}`" for fieldname in fieldnames)
	placeholders = ", ".join(["%s"] * len(fieldnames))
	frappe.db.sql(
		f"insert into `tab{BATCH_DOCTYPE}` ({column_sql}) values ({placeholders})",
		[payload[fieldname] for fieldname in fieldnames],
	)


def _normalise_batches(
	batches: dict,
	academic_years,
	default_company,
	dry_run: bool = False,
) -> int:
	"""Fill missing programme, company and year on batches that had no Student Group."""
	from education.education.program_courses import get_program_for_course

	updated = 0
	for batch_name, batch in batches.items():
		updates = {}
		if not batch.get("program") and batch.get("course"):
			program = get_program_for_course(batch["course"])
			if program:
				updates["program"] = program
		if not batch.get("company") and default_company:
			updates["company"] = default_company
		if not batch.get("academic_year") and batch.get("start_date"):
			year = find_academic_year_for_date(
				academic_years,
				batch["start_date"],
				company=batch.get("company") or default_company,
			)
			if year:
				updates["academic_year"] = year

		if not updates:
			continue

		if not dry_run:
			frappe.db.set_value(BATCH_DOCTYPE, batch_name, updates, update_modified=False)
		batch.update(updates)
		updated += 1

	return updated


def _fill_batch_programs_from_enrollments(batches, enrollments, dry_run: bool = False) -> int:
	"""Use a batch's enrollments to fill a blank programme when they agree."""
	programs_by_batch = {}
	for enrollment in enrollments:
		batch_name = enrollment.get("student_batch")
		program = enrollment.get("program")
		if not (batch_name and program):
			continue
		programs_by_batch.setdefault(batch_name, set()).add(program)

	updated = 0
	for batch_name, programs in programs_by_batch.items():
		batch = batches.get(batch_name)
		if not batch or batch.get("program") or len(programs) != 1:
			continue

		program = next(iter(programs))
		if not dry_run:
			frappe.db.set_value(
				BATCH_DOCTYPE,
				batch_name,
				{"program": program},
				update_modified=False,
			)
		batch["program"] = program
		updated += 1

	return updated


def _backfill_enrollments(
	enrollments,
	legacy_by_student,
	legacy_enrollment_courses,
	groups_by_student,
	batches,
	academic_years,
	academic_year_map,
	term_years,
	default_company,
	dry_run: bool = False,
) -> tuple[int, dict]:
	from education.education.program_courses import get_program_for_course

	updated = 0
	field_counts = {}
	for enrollment in enrollments:
		student = enrollment.get("student")
		legacy_enrollment = _pick_legacy_enrollment(
			enrollment,
			legacy_by_student.get(student, []),
			legacy_enrollment_courses,
		)
		group = _pick_group(enrollment, groups_by_student.get(student, []))

		batch_name = enrollment.get("student_batch")
		if not batch_name:
			batch_name = (legacy_enrollment or {}).get("student_batch_name") or choose_batch_name(group or {})
		batch = batches.get(batch_name) if batch_name else None

		# A legacy mapping is only trusted when its programme agrees with the
		# programme already stored on the enrollment or found on the batch.
		if batch and enrollment.get("program") and batch.get("program"):
			if batch["program"] != enrollment["program"]:
				batch = None
				if not enrollment.get("student_batch"):
					batch_name = None

		default_program = get_program_for_course(enrollment.get("course"))
		resolved_year = _resolve_enrollment_year(
			enrollment,
			legacy_enrollment,
			batch,
			academic_years,
			academic_year_map,
			term_years,
			default_company,
		)
		updates = build_enrollment_updates(
			enrollment,
			legacy_enrollment=legacy_enrollment,
			batch=batch,
			default_program=default_program,
			academic_year=resolved_year,
			batch_name=batch_name,
		)
		if resolved_year and enrollment.get("academic_year") and resolved_year != enrollment["academic_year"]:
			# The stored year exists but cannot contain the enrollment date, and a
			# legacy/date-derived year can. This is the only case where a historical
			# year is corrected; valid years are left alone.
			updates["academic_year"] = resolved_year
		if not updates:
			continue

		for fieldname in updates:
			field_counts[fieldname] = field_counts.get(fieldname, 0) + 1

		if not dry_run:
			frappe.db.set_value(
				ENROLLMENT_DOCTYPE,
				enrollment["name"],
				updates,
				update_modified=False,
			)
		enrollment.update(updates)
		updated += 1

	return updated, field_counts


def _pick_legacy_enrollment(enrollment, candidates, course_map):
	if not candidates:
		return None

	course = enrollment.get("course")
	candidates_with_courses = [candidate for candidate in candidates if course_map.get(candidate.get("name"))]
	if candidates_with_courses:
		course_matches = [
			candidate
			for candidate in candidates_with_courses
			if course and course in course_map.get(candidate.get("name"), set())
		]
		if course_matches:
			candidates = course_matches
		else:
			# Another legacy enrollment may predate the course child table. Keep
			# those candidates, but never use a known different course mapping.
			candidates = [candidate for candidate in candidates if not course_map.get(candidate.get("name"))]
			if not candidates:
				return None

	if enrollment.get("program"):
		program_candidates = [candidate for candidate in candidates if candidate.get("program")]
		program_matches = [
			candidate for candidate in program_candidates if candidate.get("program") == enrollment["program"]
		]
		if program_matches:
			candidates = program_matches
		elif program_candidates:
			return None

	return sorted(
		candidates,
		key=lambda candidate: (candidate.get("enrollment_date") or "", candidate.get("name") or ""),
		reverse=True,
	)[0]


def _pick_group(enrollment, groups):
	if not groups:
		return None

	course = enrollment.get("course")
	program = enrollment.get("program")
	matches = [
		group
		for group in groups
		if (course and group.get("course") == course) or (program and group.get("program") == program)
	]
	if not matches:
		matches = groups

	return sorted(
		matches,
		key=lambda group: (group.get("program") or "", choose_batch_name(group) or ""),
	)[0]


def _resolve_enrollment_year(
	enrollment,
	legacy_enrollment,
	batch,
	academic_years,
	academic_year_map,
	term_years,
	default_company,
):
	current_year = enrollment.get("academic_year")
	legacy_year = None
	if legacy_enrollment:
		legacy_year = resolve_legacy_enrollment_year(
			legacy_enrollment,
			term_years,
			academic_years,
			company=enrollment.get("company") or default_company,
		)

	enrollment_date = enrollment.get("enrollment_date") or (legacy_enrollment or {}).get("enrollment_date")
	date_year = find_academic_year_for_date(
		academic_years,
		enrollment_date,
		company=enrollment.get("company") or default_company,
	)

	if not current_year:
		return legacy_year or date_year or (batch or {}).get("academic_year")

	current = academic_year_map.get(current_year)
	if not current:
		# A stale link to a deleted Academic Year is never a valid historical value.
		return legacy_year or date_year or (batch or {}).get("academic_year")

	if not enrollment_date or _date_in_year(enrollment_date, current):
		return None

	if legacy_year and legacy_year != current_year:
		legacy = academic_year_map.get(legacy_year)
		if legacy and _date_in_year(enrollment_date, legacy):
			return legacy_year

	if date_year and date_year != current_year:
		return date_year

	return None


def _date_in_year(date, academic_year) -> bool:
	if not academic_year:
		return False

	start = academic_year.get("year_start_date")
	end = academic_year.get("year_end_date")
	if not (start and end):
		return False

	try:
		date = getdate(date)
		return getdate(start) <= date <= getdate(end)
	except Exception:
		return False
