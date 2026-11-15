# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt


import frappe
from frappe.tests.utils import FrappeTestCase

from education.education.batch_enrollment_migration import (
	_resolve_enrollment_year,
	build_batch_plan,
	build_enrollment_updates,
	choose_batch_name,
	find_academic_year_for_date,
	resolve_legacy_enrollment_year,
)

# test_records = frappe.get_test_records('Student Batch Name')


class TestStudentBatchName(FrappeTestCase):
	def test_batch_meta_makes_program_primary_and_course_optional(self):
		meta = frappe.get_meta("Student Batch Name")

		program = meta.get_field("program")
		self.assertEqual(program.fieldtype, "Link")
		self.assertEqual(program.options, "Program")
		self.assertTrue(program.reqd)
		self.assertFalse(program.read_only)
		self.assertFalse(program.fetch_from)

		course = meta.get_field("course")
		self.assertEqual(course.fieldtype, "Link")
		self.assertFalse(course.reqd)

		self.assertTrue(meta.has_field("academic_year"))
		self.assertTrue(meta.has_field("max_strength"))
		self.assertTrue(meta.has_field("disabled"))

	def test_enrollment_meta_has_explicit_program_and_academic_year(self):
		meta = frappe.get_meta("Course Enrollment")

		program = meta.get_field("program")
		self.assertTrue(program.reqd)
		self.assertFalse(program.read_only)
		self.assertFalse(program.fetch_from)

		academic_year = meta.get_field("academic_year")
		self.assertEqual(academic_year.fieldtype, "Link")
		self.assertEqual(academic_year.options, "Academic Year")
		self.assertTrue(academic_year.reqd)

	def test_schedule_and_assessment_derive_program_not_course(self):
		for doctype in ("Subject Schedule", "Assessment Plan"):
			meta = frappe.get_meta(doctype)
			self.assertTrue(meta.has_field("program"), doctype)

			course = meta.get_field("course")
			self.assertFalse(course.fetch_from, doctype)

	def test_choose_batch_name_prefers_legacy_batch_link(self):
		self.assertEqual(
			choose_batch_name(
				{"batch": "_Batch 1", "student_group_name": "_Section A", "name": "_Section A"}
			),
			"_Batch 1",
		)
		self.assertEqual(choose_batch_name({"student_group_name": "_Section A"}), "_Section A")

	def test_find_academic_year_for_date_is_conservative(self):
		years = [
			{"name": "2023-2024", "year_start_date": "2023-04-01", "year_end_date": "2024-03-31"},
			{"name": "2024-2025", "year_start_date": "2024-04-01", "year_end_date": "2025-03-31"},
		]
		self.assertEqual(find_academic_year_for_date(years, "2023-08-01"), "2023-2024")
		self.assertIsNone(find_academic_year_for_date(years, "2026-08-01"))

		overlapping = [
			*years,
			{"name": "_Other 2023", "year_start_date": "2023-01-01", "year_end_date": "2023-12-31"},
		]
		self.assertIsNone(find_academic_year_for_date(overlapping, "2023-08-01"))

	def test_build_batch_plan_creates_from_group(self):
		plan = build_batch_plan(
			{
				"student_group_name": "_Batch A",
				"program": "_Program",
				"course": "_Course",
				"max_strength": "40",
				"disabled": "0",
			},
			academic_year={
				"name": "2023-2024",
				"year_start_date": "2023-04-01",
				"year_end_date": "2024-03-31",
			},
			company="_Test Company",
		)
		self.assertEqual(plan["action"], "create")
		self.assertEqual(plan["name"], "_Batch A")
		self.assertEqual(plan["values"]["program"], "_Program")
		self.assertEqual(plan["values"]["academic_year"], "2023-2024")
		self.assertEqual(plan["values"]["max_strength"], 40)

	def test_build_batch_plan_only_fills_blanks_on_existing_batch(self):
		plan = build_batch_plan(
			{"batch": "_Batch A", "program": "_Other Program", "course": "_Other Course"},
			existing_batch={
				"name": "_Batch A",
				"program": "_Program",
				"course": None,
				"company": "_Test Company",
				"max_strength": 0,
				"disabled": 0,
				"academic_year": "2023-2024",
				"start_date": "2023-04-01",
				"end_date": "2024-03-31",
			},
			academic_year={"name": "2023-2024"},
			company="_Test Company",
		)
		self.assertEqual(plan["values"], {"course": "_Other Course"})

	def test_build_enrollment_updates_never_overwrites_existing_values(self):
		self.assertEqual(
			build_enrollment_updates(
				{
					"program": "_Program",
					"student_batch": "_Batch",
					"academic_year": "2023-2024",
				},
				legacy_enrollment={"program": "_Other", "student_batch_name": "_Other Batch"},
				batch={"name": "_Other Batch", "program": "_Other"},
				academic_year="2024-2025",
			),
			{},
		)

		self.assertEqual(
			build_enrollment_updates(
				{"program": None, "student_batch": None, "academic_year": None},
				legacy_enrollment={"program": "_Program", "student_batch_name": "_Batch"},
				batch={"name": "_Batch", "program": "_Program"},
				academic_year="2023-2024",
			),
			{"program": "_Program", "student_batch": "_Batch", "academic_year": "2023-2024"},
		)

	def test_resolve_legacy_enrollment_year_from_explicit_term_and_date(self):
		years = [
			{"name": "2023-2024", "year_start_date": "2023-04-01", "year_end_date": "2024-03-31"},
		]
		self.assertEqual(
			resolve_legacy_enrollment_year({"academic_year": "2023-2024"}),
			"2023-2024",
		)
		self.assertEqual(
			resolve_legacy_enrollment_year({"intake_year": "2022-2023"}),
			"2022-2023",
		)
		self.assertEqual(
			resolve_legacy_enrollment_year(
				{"academic_term": "_Term"},
				term_years={"_Term": "2021-2022"},
			),
			"2021-2022",
		)
		self.assertEqual(
			resolve_legacy_enrollment_year(
				{"enrollment_date": "2023-08-01"},
				academic_years=years,
			),
			"2023-2024",
		)

	def test_academic_year_is_corrected_only_when_stored_year_is_impossible(self):
		years = [
			{"name": "2022-2023", "year_start_date": "2022-04-01", "year_end_date": "2023-03-31"},
			{"name": "2023-2024", "year_start_date": "2023-04-01", "year_end_date": "2024-03-31"},
		]
		year_map = {year["name"]: year for year in years}

		# Valid stored year for the enrollment date: never overwrite it.
		self.assertIsNone(
			_resolve_enrollment_year(
				{"academic_year": "2023-2024", "enrollment_date": "2023-08-01"},
				None,
				None,
				years,
				year_map,
				{},
				None,
			)
		)

		# Stored year cannot contain the date, legacy Program Enrollment confirms the
		# correct year: correct it.
		self.assertEqual(
			_resolve_enrollment_year(
				{"academic_year": "2022-2023", "enrollment_date": "2023-08-01"},
				{"academic_year": "2023-2024"},
				None,
				years,
				year_map,
				{},
				None,
			),
			"2023-2024",
		)
