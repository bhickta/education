# Copyright (c) 2026, Himguru Technologies and Contributors
# See license.txt


import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint

from education.education.doctype.program.test_program import make_course, make_program
from education.patches.v17_0.restore_program_courses import (
	execute as restore_program_courses,
)


class TestProgramCourse(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_new_row_defaults(self):
		row = frappe.new_doc("Program Course")
		self.assertEqual(cint(row.required), 1)
		self.assertEqual(cint(row.is_active), 1)

	def test_migration_populates_from_course_program_and_is_idempotent(self):
		program = make_program("_Test Program Course Migration")
		course = make_course(
			"_Test Program Course Migration Course",
			company=frappe.db.get_value("Program", program, "company"),
			program=program,
		)
		frappe.db.delete("Program Course", {"parent": program})

		first = restore_program_courses()
		self.assertGreaterEqual(first["created"], 1)

		rows = frappe.get_all(
			"Program Course",
			filters={"parent": program, "parenttype": "Program", "parentfield": "courses"},
			fields=["course", "course_name", "required", "is_active"],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].course, course)
		self.assertEqual(rows[0].course_name, "_Test Program Course Migration Course")
		self.assertEqual(cint(rows[0].required), 1)
		self.assertEqual(cint(rows[0].is_active), 1)
		self.assertEqual(frappe.db.get_value("Course", course, "program"), program)

		restore_program_courses()

		self.assertEqual(
			frappe.db.count(
				"Program Course",
				{"parent": program, "course": course},
			),
			1,
		)

	def test_migration_normalises_legacy_rows_without_reassigning_course(self):
		program = make_program("_Test Program Course Legacy")
		course = make_course(
			"_Test Program Course Legacy Course",
			company=frappe.db.get_value("Program", program, "company"),
		)

		program_doc = frappe.get_doc("Program", program)
		program_doc.append("courses", {"course": course, "required": 1})
		program_doc.flags.ignore_mandatory = True
		program_doc.save()
		row_name = program_doc.courses[0].name

		# Simulate a row written before parent metadata and the new columns existed.
		frappe.db.sql(
			"""update `tabProgram Course`
			set parenttype = '', parentfield = '', course_name = null,
				required = null, is_active = null, sort_order = null
			where name = %s""",
			row_name,
		)

		restore_program_courses()

		row = frappe.db.get_value(
			"Program Course",
			row_name,
			["parenttype", "parentfield", "course_name", "required", "is_active", "sort_order"],
			as_dict=True,
		)
		self.assertEqual(row.parenttype, "Program")
		self.assertEqual(row.parentfield, "courses")
		self.assertEqual(row.course_name, "_Test Program Course Legacy Course")
		self.assertEqual(cint(row.required), 1)
		self.assertEqual(cint(row.is_active), 1)
		self.assertEqual(cint(row.sort_order), 1)
		self.assertEqual(frappe.db.count("Program Course", {"parent": program, "course": course}), 1)
