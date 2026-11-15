# Copyright (c) 2015, Frappe Technologies and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from education.education.program_courses import (
	get_program_course_names,
	is_multi_company,
)


class Program(Document):
	def validate(self):
		self.validate_unit_load()
		self.validate_department_company()
		self.validate_courses()

	def get_course_list(self):
		"""Return Course documents for this programme's curriculum."""
		if self.name:
			course_names = get_program_course_names(self.name)
		else:
			course_names = [
				row.course
				for row in self.get("courses") or []
				if row.course and (row.get("is_active") is None or cint(row.get("is_active")))
			]

		course_list = []
		seen = set()
		for course_name in course_names:
			if course_name in seen or not frappe.db.exists("Course", course_name):
				continue
			seen.add(course_name)
			course_list.append(frappe.get_doc("Course", course_name))
		return course_list

	def validate_unit_load(self):
		if (
			self.minimum_unit_load
			and self.maximum_unit_load
			and self.minimum_unit_load > self.maximum_unit_load
		):
			frappe.throw(_("Minimum Unit Load cannot exceed Maximum Unit Load."))

	def validate_department_company(self):
		if not self.department or not self.company:
			return

		department_company = frappe.db.get_value("Department", self.department, "company")
		if department_company != self.company:
			frappe.throw(
				_("Department {0} does not belong to Company {1}.").format(
					frappe.bold(self.department), frappe.bold(self.company)
				)
			)

	def validate_courses(self):
		rows = self.get("courses") or []
		seen = {}

		for row in rows:
			if not row.course:
				continue

			if not frappe.db.exists("Course", row.course):
				frappe.throw(
					_("Row {0}: Course {1} does not exist.").format(row.idx, frappe.bold(row.course))
				)

			if row.course in seen:
				frappe.throw(
					_("Row {0}: Course {1} is already added in row {2}.").format(
						row.idx, frappe.bold(row.course), seen[row.course]
					)
				)
			seen[row.course] = row.idx

		# Company checks only make sense when the site actually uses multiple companies.
		if not self.company or not is_multi_company():
			return

		for row in rows:
			if not row.course:
				continue

			course_company = frappe.db.get_value("Course", row.course, "company")
			if course_company and course_company != self.company:
				frappe.throw(
					_("Row {0}: Course {1} belongs to Company {2}, not Company {3}.").format(
						row.idx,
						frappe.bold(row.course),
						frappe.bold(course_company),
						frappe.bold(self.company),
					)
				)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_program_courses(
	doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict | None
):
	filters = filters or {}
	program = filters.get("program")
	if not program:
		frappe.msgprint(_("Please select a Program first."))
		return []

	course_names = get_program_course_names(program)
	if not course_names:
		return []

	company = filters.get("company")
	exclude_courses = filters.get("exclude_courses") or []
	if isinstance(exclude_courses, str):
		try:
			exclude_courses = frappe.parse_json(exclude_courses)
		except ValueError:
			exclude_courses = [exclude_courses]
	exclude_courses = set(exclude_courses or [])

	courses = frappe.get_all(
		"Course",
		filters={"name": ("in", course_names)},
		fields=["name", "course_name", "company"],
	)
	order = {course_name: idx for idx, course_name in enumerate(course_names)}
	txt = (txt or "").lower()
	matches = [
		course
		for course in courses
		if course.name not in exclude_courses
		and (not company or course.company == company)
		and (txt in (course.name or "").lower() or txt in (course.course_name or "").lower())
	]
	matches.sort(key=lambda course: order.get(course.name, len(course_names)))

	start = cint(start)
	page_len = cint(page_len)
	return [(course.name, course.course_name or course.name) for course in matches[start : start + page_len]]
