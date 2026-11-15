# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from education.education.doctype.campus.campus import apply_room_campus
from education.education.program_courses import course_belongs_to_program


class AssessmentPlan(Document):
	def validate(self):
		apply_room_campus(self)
		self.set_program_from_batch()
		self.validate_course()
		self.validate_overlap()
		self.validate_max_score()
		self.validate_subject()
		self.validate_academic_year_and_term()
		self.validate_company()

	def set_program_from_batch(self):
		batch_program = frappe.db.get_value("Student Batch Name", self.student_batch, "program")
		if not batch_program:
			frappe.throw(
				_("Student Batch {0} does not have a Program.").format(frappe.bold(self.student_batch))
			)

		self.program = batch_program

	def validate_course(self):
		"""The course is chosen from the batch programme, not copied from the batch."""
		batch_course = frappe.db.get_value("Student Batch Name", self.student_batch, "course")
		if batch_course and self.course and batch_course != self.course:
			frappe.throw(
				_("Batch {0} belongs to Course {1}, not to Course {2}.").format(
					frappe.bold(self.student_batch),
					frappe.bold(batch_course),
					frappe.bold(self.course),
				)
			)

		if self.course and not course_belongs_to_program(self.program, self.course):
			frappe.throw(
				_("Course {0} is not part of the curriculum of Program {1}.").format(
					frappe.bold(self.course),
					frappe.bold(self.program),
				)
			)

	def validate_subject(self):
		if not (self.subject and self.course):
			return

		subject_course = frappe.db.get_value("Subject", self.subject, "course")
		if subject_course and subject_course != self.course:
			frappe.throw(
				_("Subject {0} does not belong to Course {1}").format(
					frappe.bold(self.subject), frappe.bold(self.course)
				)
			)

	def validate_academic_year_and_term(self):
		if not self.academic_year:
			frappe.throw(_("Academic Year is mandatory"))

		self._validate_date_in_period(
			"Academic Year",
			self.academic_year,
			["year_start_date", "year_end_date"],
		)

		if not self.academic_term:
			return

		term = frappe.db.get_value(
			"Academic Term",
			self.academic_term,
			["academic_year", "term_start_date", "term_end_date"],
			as_dict=True,
		)
		if not term:
			return

		if term.academic_year != self.academic_year:
			frappe.throw(
				_("Academic Term {0} does not belong to Academic Year {1}").format(
					frappe.bold(self.academic_term), frappe.bold(self.academic_year)
				)
			)

		self._validate_date_in_period(
			"Academic Term",
			self.academic_term,
			["term_start_date", "term_end_date"],
			dates=term,
		)

	def _validate_date_in_period(self, doctype, name, date_fields, dates=None):
		if not self.schedule_date:
			return

		dates = dates or frappe.db.get_value(doctype, name, date_fields, as_dict=True)
		if not dates:
			return

		schedule_date = getdate(self.schedule_date)
		start = dates.get(date_fields[0])
		end = dates.get(date_fields[1])

		if start and schedule_date < getdate(start):
			frappe.throw(
				_("Schedule Date cannot be before the start of {0} {1}").format(_(doctype), frappe.bold(name))
			)

		if end and schedule_date > getdate(end):
			frappe.throw(
				_("Schedule Date cannot be after the end of {0} {1}").format(_(doctype), frappe.bold(name))
			)

	def validate_company(self):
		if not self.company:
			return

		for doctype, value in (
			("Student Batch Name", self.student_batch),
			("Program", self.program),
			("Course", self.course),
			("Academic Year", self.academic_year),
			("Academic Term", self.academic_term),
		):
			if not value:
				continue

			company = frappe.db.get_value(doctype, value, "company")
			if company and company != self.company:
				frappe.throw(
					_("Company must be the same as that of {0} {1}").format(_(doctype), frappe.bold(value))
				)

	def validate_overlap(self):
		"""Validates overlap for Batch, Faculty, Room"""

		from education.education.utils import validate_overlap_for

		# Validate overlapping subject schedules.
		if self.student_batch:
			validate_overlap_for(self, "Subject Schedule", "student_batch")

		if self.faculty:
			validate_overlap_for(self, "Subject Schedule", "faculty", self.faculty)
		validate_overlap_for(self, "Subject Schedule", "room")

		# validate overlapping assessment schedules.
		if self.student_batch:
			validate_overlap_for(self, "Assessment Plan", "student_batch")

		validate_overlap_for(self, "Assessment Plan", "room")
		validate_overlap_for(self, "Room Booking", "room")

	def validate_max_score(self):
		if flt(self.maximum_assessment_score) <= 0:
			frappe.throw(_("Maximum Score must be greater than zero"))
