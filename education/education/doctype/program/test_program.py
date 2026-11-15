# Copyright (c) 2015, Frappe Technologies and Contributors
# See license.txt


from unittest.mock import patch

import frappe
from erpnext import get_default_company
from frappe.tests.utils import FrappeTestCase

from education.education.doctype.program.program import get_program_courses
from education.education.program_courses import (
	get_program_course_names,
	get_program_course_rows,
)


class TestProgram(FrappeTestCase):
	def setUp(self):
		make_program_and_linked_courses("_Test Program 1", ["_Test Course 1", "_Test Course 2"])

	def tearDown(self):
		frappe.db.rollback()

	def test_get_course_list(self):
		program = frappe.get_doc("Program", "_Test Program 1")
		courses = program.get_course_list()
		self.assertEqual([course.name for course in courses], ["_Test Course 1", "_Test Course 2"])

	def test_course_link_search_uses_curriculum(self):
		results = get_program_courses(
			"Course",
			"",
			"name",
			0,
			20,
			{"program": "_Test Program 1"},
		)
		self.assertEqual([row[0] for row in results], ["_Test Course 1", "_Test Course 2"])

		results = get_program_courses(
			"Course",
			"",
			"name",
			0,
			20,
			{"program": "_Test Program 1", "exclude_courses": ["_Test Course 1"]},
		)
		self.assertEqual([row[0] for row in results], ["_Test Course 2"])

	def test_rejects_duplicate_course(self):
		program = frappe.get_doc("Program", make_program("_Test Duplicate Program"))
		course = make_course("_Test Duplicate Course", company=program.company)
		program.append("courses", {"course": course, "required": 1})
		program.append("courses", {"course": course, "required": 1})
		program.flags.ignore_mandatory = True

		self.assertRaises(frappe.ValidationError, program.save)

	def test_rejects_missing_course(self):
		program = frappe.get_doc("Program", make_program("_Test Missing Course Program"))
		program.append("courses", {"course": "_Test Missing Course", "required": 1})
		program.flags.ignore_mandatory = True

		self.assertRaises(frappe.ValidationError, program.save)

	def test_company_mismatch_is_checked_only_for_multi_company_sites(self):
		program = frappe.get_doc("Program", make_program("_Test Company Program"))
		course = make_course("_Test Other Company Course", company=f"{program.company} Other")
		program.append("courses", {"course": course, "required": 1})
		program.flags.ignore_mandatory = True

		with patch(
			"education.education.doctype.program.program.is_multi_company",
			return_value=True,
		):
			self.assertRaises(frappe.ValidationError, program.save)

		with patch(
			"education.education.doctype.program.program.is_multi_company",
			return_value=False,
		):
			program.save()

	def test_get_course_list_falls_back_to_course_program(self):
		program = make_program("_Test Fallback Program")
		course = make_course(
			"_Test Fallback Course",
			company=frappe.db.get_value("Program", program, "company"),
			program=program,
		)

		self.assertEqual(get_program_course_names(program), [course])
		rows = get_program_course_rows(program)
		self.assertEqual(rows[0].source, "course.program")

	def test_program_course_rows_are_preferred_over_course_program(self):
		program = make_program("_Test Preferred Program")
		legacy_course = make_course(
			"_Test Legacy Linked Course",
			company=frappe.db.get_value("Program", program, "company"),
			program=program,
		)
		curriculum_course = make_course(
			"_Test Curriculum Course",
			company=frappe.db.get_value("Program", program, "company"),
		)

		program_doc = frappe.get_doc("Program", program)
		program_doc.append("courses", {"course": curriculum_course, "required": 1})
		program_doc.flags.ignore_mandatory = True
		program_doc.save()

		self.assertNotEqual(legacy_course, curriculum_course)
		self.assertEqual(get_program_course_names(program), [curriculum_course])
		self.assertEqual(get_program_course_rows(program)[0].source, "program_course")


def get_test_company():
	return get_default_company() or frappe.db.get_value("Company", {}, "name")


def make_program(name):
	if frappe.db.exists("Program", name):
		return name

	program = frappe.get_doc(
		{
			"doctype": "Program",
			"program_name": name,
			"program_abbreviation": name[:20],
			"company": get_test_company(),
		}
	)
	program.insert(ignore_mandatory=True, ignore_links=True)
	return program.name


def make_course(name, company=None, program=None):
	if frappe.db.exists("Course", name):
		return name

	course = frappe.get_doc(
		{
			"doctype": "Course",
			"course_name": name,
			"course_abbreviation": name[:20],
			"company": company or get_test_company(),
			"program": program,
		}
	)
	course.insert(ignore_mandatory=True, ignore_links=True)
	return course.name


def make_program_and_linked_courses(program_name, course_name_list):
	program = frappe.get_doc("Program", make_program(program_name))
	existing = {row.course for row in program.courses or []}
	for course_name in course_name_list:
		course = make_course(course_name, company=program.company)
		if course in existing:
			continue
		program.append("courses", {"course": course, "required": 1})
		existing.add(course)

	program.flags.ignore_mandatory = True
	program.flags.ignore_links = True
	program.save()
	return program
