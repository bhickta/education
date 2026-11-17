"""Focused tests for the Student primary Contact and compatibility mirrors."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from education.education.doctype.student.student_contact import (
	get_contact_primary_email,
	get_contact_primary_phone,
	sync_contact_mirror_fields,
)


class TestStudentPrimaryContact(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _student(self, **values):
		suffix = frappe.generate_hash(length=8)
		doc = frappe.get_doc(
			{
				"doctype": "Student",
				"first_name": "Mirror",
				"last_name": suffix,
				"email_address": f"mirror.{suffix}@example.com",
				**values,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_contact_created_from_legacy_values(self):
		student = self._student(
			student_email_id=f"legacy.{frappe.generate_hash(length=8)}@example.com",
			student_mobile_number="+91 90000 00001",
		)

		self.assertTrue(student.primary_contact)
		contact = frappe.get_doc("Contact", student.primary_contact)
		self.assertEqual(get_contact_primary_email(contact), student.student_email_id)
		self.assertEqual(get_contact_primary_phone(contact), student.student_mobile_number)

	def test_contact_edit_refreshes_mirror_without_data_loss(self):
		email = f"before.{frappe.generate_hash(length=8)}@example.com"
		student = self._student(
			student_email_id=email,
			student_mobile_number="+91 90000 00002",
		)
		contact = frappe.get_doc("Contact", student.primary_contact)
		contact.email_ids[0].email_id = f"after.{frappe.generate_hash(length=8)}@example.com"
		contact.phone_nos[0].phone = ""
		contact.save(ignore_permissions=True)

		student.reload()
		self.assertEqual(student.student_email_id, contact.email_ids[0].email_id)
		# An empty phone on the Contact must not erase the historical mobile.
		self.assertEqual(student.student_mobile_number, "+91 90000 00002")

	def test_sync_leaves_legacy_values_when_no_primary_contact(self):
		suffix = frappe.generate_hash(length=8)
		student = frappe.get_doc(
			{
				"doctype": "Student",
				"naming_series": "EDU-STU-.YYYY.-",
				"first_name": "NoContact",
				"last_name": suffix,
				"email_address": f"nocontact.{suffix}@example.com",
				"student_email_id": f"legacy.{suffix}@example.com",
				"student_mobile_number": "+91 90000 00003",
			}
		)
		# Simulate a historical row that predates the Contact migration.
		student.flags.ignore_validate = True
		student.db_insert()

		self.assertFalse(student.primary_contact)
		self.assertFalse(sync_contact_mirror_fields(student))
		self.assertEqual(student.student_email_id, f"legacy.{suffix}@example.com")
		self.assertEqual(student.student_mobile_number, "+91 90000 00003")
