"""Create/link the Student primary Contact and Address from legacy values.

The Student form now edits contact details through the primary Contact. This
patch keeps existing records working:

* attach an already linked Contact/Address where one exists,
* create a Contact (and, when address lines are present, an Address) from the
  legacy ``student_email_id``/``student_mobile_number``/address columns,
* copy the primary Contact email and phone onto the hidden compatibility
  columns so reports, searches, portals and print formats keep working.

No Student value is deleted. The legacy columns remain in place.
"""

from __future__ import annotations

import frappe

from education.education.doctype.student.student_contact import (
	CONTACT,
	EMAIL_MIRROR_FIELD,
	MOBILE_MIRROR_FIELD,
	STUDENT,
	ensure_primary_address,
	ensure_primary_contact,
	get_contact_primary_email,
	get_contact_primary_phone,
)


def execute() -> None:
	if not frappe.db.has_column(STUDENT, "primary_contact"):
		return

	_drop_unique_email_index()

	fields = [
		fieldname
		for fieldname in (
			"name",
			"student_name",
			"first_name",
			"last_name",
			"email_address",
			"primary_contact",
			"primary_address",
			"gender",
			"address_line_1",
			"address_line_2",
			"city",
			"state",
			"pincode",
			"country",
			EMAIL_MIRROR_FIELD,
			MOBILE_MIRROR_FIELD,
		)
		if frappe.db.has_column(STUDENT, fieldname)
	]

	for row in frappe.get_all(STUDENT, fields=fields):
		contact = ensure_primary_contact(row)
		address = ensure_primary_address(row)

		updates: dict[str, str] = {}
		if contact and row.get("primary_contact") != contact:
			updates["primary_contact"] = contact
		if address and row.get("primary_address") != address:
			updates["primary_address"] = address

		if contact:
			contact_doc = frappe.get_doc(CONTACT, contact)
			email = get_contact_primary_email(contact_doc)
			phone = get_contact_primary_phone(contact_doc)
			if email and row.get(EMAIL_MIRROR_FIELD) != email:
				updates[EMAIL_MIRROR_FIELD] = email
			if phone and row.get(MOBILE_MIRROR_FIELD) != phone:
				updates[MOBILE_MIRROR_FIELD] = phone

		if updates:
			frappe.db.set_value(STUDENT, row.name, updates, update_modified=False)


def _drop_unique_email_index() -> None:
	"""Allow family members to share a primary Contact email.

	``student_email_id`` used to be unique. It is now a compatibility mirror of
	the primary Contact and must accept the same address on siblings.
	"""
	if not frappe.db.has_column(STUDENT, EMAIL_MIRROR_FIELD):
		return
	indexes = frappe.db.sql(
		"""
		show index from `tabStudent`
		where Column_name = %s and Non_unique = 0
		""",
		EMAIL_MIRROR_FIELD,
		as_dict=True,
	)
	for index in indexes:
		if index.Key_name == "PRIMARY":
			continue
		frappe.db.sql(f"alter table `tabStudent` drop index `{index.Key_name}`")
