# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt


from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCourseEnrollment(FrappeTestCase):
	def test_program_is_not_cleared_when_course_is_empty(self):
		enrollment = frappe.get_doc({"doctype": "Course Enrollment", "program": "_Program"})

		enrollment.set_program_from_course()

		self.assertEqual(enrollment.program, "_Program")

	def test_program_only_defaults_when_course_has_one_program(self):
		enrollment = frappe.get_doc({"doctype": "Course Enrollment"})

		with patch(
			"education.education.doctype.course_enrollment.course_enrollment.get_program_for_course",
			return_value="_Only Program",
		):
			enrollment.set_program_from_course()
		self.assertEqual(enrollment.program, "_Only Program")

	def test_program_is_not_guessed_when_course_is_ambiguous(self):
		enrollment = frappe.get_doc({"doctype": "Course Enrollment"})

		with patch(
			"education.education.doctype.course_enrollment.course_enrollment.get_program_for_course",
			return_value=None,
		):
			enrollment.set_program_from_course()
		self.assertIsNone(enrollment.program)

	def test_academic_year_defaults_from_admission_register(self):
		enrollment = frappe.get_doc({"doctype": "Course Enrollment", "admission_register": "_Admission"})

		with patch(
			"education.education.doctype.course_enrollment.course_enrollment.frappe.db.get_value",
			return_value="2023-2024",
		):
			enrollment.set_academic_year_from_register()

		self.assertEqual(enrollment.academic_year, "2023-2024")
