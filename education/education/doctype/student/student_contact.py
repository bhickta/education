"""Student primary Contact/Address integration.

Student keeps the historical ``student_email_id`` and ``student_mobile_number``
columns as hidden, read-only mirrors so reports, searches, portals and print
formats that still read those columns keep working. The primary Contact is the
editable source of truth; these helpers create the primary records from legacy
values, copy the primary email/phone back onto the mirror columns and keep the
mirrors fresh when a Contact is edited.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

import frappe

STUDENT = "Student"
CONTACT = "Contact"
ADDRESS = "Address"
EMAIL_MIRROR_FIELD = "student_email_id"
MOBILE_MIRROR_FIELD = "student_mobile_number"

CONTACT_FIELDS = (
	"name",
	"student_name",
	"first_name",
	"last_name",
	"email_address",
	EMAIL_MIRROR_FIELD,
	MOBILE_MIRROR_FIELD,
	"gender",
	"primary_contact",
	"primary_address",
	"address_line_1",
	"address_line_2",
	"city",
	"state",
	"pincode",
	"country",
)


def _get(student: Any, fieldname: str) -> Any:
	if isinstance(student, MutableMapping):
		return student.get(fieldname)
	return getattr(student, fieldname, None)


def _set(student: Any, fieldname: str, value: Any) -> None:
	if isinstance(student, MutableMapping):
		student[fieldname] = value
	else:
		setattr(student, fieldname, value)


def get_contact_primary_email(contact: Any) -> str:
	"""Return the Contact's primary email, falling back to its first email row."""
	email = (contact.get("email_id") or "").strip()
	if email:
		return email
	rows = contact.get("email_ids") or []
	for row in rows:
		if row.get("is_primary") and (row.get("email_id") or "").strip():
			return row.email_id.strip()
	for row in rows:
		if (row.get("email_id") or "").strip():
			return row.email_id.strip()
	return ""


def get_contact_primary_phone(contact: Any) -> str:
	"""Return the Contact's primary mobile/phone, falling back to the first number."""
	for fieldname in ("mobile_no", "phone"):
		value = (contact.get(fieldname) or "").strip()
		if value:
			return value
	rows = contact.get("phone_nos") or []
	for flag in ("is_primary_mobile_no", "is_primary_phone"):
		for row in rows:
			if row.get(flag) and (row.get("phone") or "").strip():
				return row.phone.strip()
	for row in rows:
		if (row.get("phone") or "").strip():
			return row.phone.strip()
	return ""


def get_linked_record(doctype: str, student: str) -> str | None:
	"""Return the oldest record already linked to the Student, if any."""
	if not student:
		return None
	rows = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": STUDENT, "link_name": student, "parenttype": doctype},
		pluck="parent",
		order_by="creation asc",
		limit=1,
	)
	return rows[0] if rows else None


def ensure_primary_contact(student: Any) -> str | None:
	"""Attach the Student's existing Contact or create one from legacy values.

	The function is idempotent: a valid ``primary_contact`` is kept, an existing
	linked Contact is reused before a new one is created, and nothing is created
	when the Student has neither an email nor a mobile number.
	"""
	name = _get(student, "name")
	existing = (_get(student, "primary_contact") or "").strip()
	if existing and frappe.db.exists(CONTACT, existing):
		return existing

	contact = get_linked_record(CONTACT, name) or _create_contact(student)
	if contact:
		_set(student, "primary_contact", contact)
	return contact


def _create_contact(student: Any) -> str | None:
	name = _get(student, "name")
	if not name:
		return None
	email = (_get(student, EMAIL_MIRROR_FIELD) or _get(student, "email_address") or "").strip()
	mobile = (_get(student, MOBILE_MIRROR_FIELD) or "").strip()
	if not email and not mobile:
		return None

	full_name = (_get(student, "student_name") or "").strip()
	first_name = (_get(student, "first_name") or "").strip()
	last_name = (_get(student, "last_name") or "").strip()
	if not first_name:
		first_name = full_name.split(" ", 1)[0] if full_name else name
	if not last_name and full_name and " " in full_name:
		last_name = full_name.split(" ", 1)[1].strip()

	gender = _get(student, "gender")
	if gender and not frappe.db.exists("Gender", gender):
		gender = None

	contact = frappe.get_doc(
		{
			"doctype": CONTACT,
			"first_name": first_name[:120],
			"last_name": last_name[:120] or None,
			"gender": gender,
			"is_primary_contact": 1,
			"email_ids": [{"email_id": email, "is_primary": 1}] if email else [],
			"phone_nos": [
				{
					"phone": mobile,
					"is_primary_phone": 1,
					"is_primary_mobile_no": 1,
				}
			]
			if mobile
			else [],
			"links": [{"link_doctype": STUDENT, "link_name": _get(student, "name")}],
		}
	)
	contact.flags.ignore_permissions = True
	contact.insert()
	return contact.name


def ensure_primary_address(student: Any) -> str | None:
	"""Attach the Student's existing Address or create one from legacy address fields."""
	name = _get(student, "name")
	existing = (_get(student, "primary_address") or "").strip()
	if existing and frappe.db.exists(ADDRESS, existing):
		return existing

	address = get_linked_record(ADDRESS, name) or _create_address(student)
	if address:
		_set(student, "primary_address", address)
	return address


def _create_address(student: Any) -> str | None:
	name = _get(student, "name")
	if not name:
		return None
	line1 = (_get(student, "address_line_1") or "").strip()
	line2 = (_get(student, "address_line_2") or "").strip()
	# Address requires address_line1. Leave records that only carry a city or
	# state without a linked Address instead of inventing a street line.
	if not line1 and not line2:
		return None
	if not line1:
		line1, line2 = line2, ""

	country = (_get(student, "country") or "").strip()
	if not country or not frappe.db.exists("Country", country):
		country = "India"

	address = frappe.get_doc(
		{
			"doctype": ADDRESS,
			"address_title": (_get(student, "student_name") or _get(student, "name") or "")[:120],
			"address_type": "Personal",
			"address_line1": line1,
			"address_line2": line2 or None,
			"city": _get(student, "city"),
			"state": _get(student, "state"),
			"pincode": _get(student, "pincode"),
			"country": country,
			"email_id": _get(student, EMAIL_MIRROR_FIELD) or _get(student, "email_address"),
			"phone": _get(student, MOBILE_MIRROR_FIELD),
			"is_primary_address": 1,
			"links": [{"link_doctype": STUDENT, "link_name": _get(student, "name")}],
		}
	)
	address.flags.ignore_permissions = True
	address.insert()
	return address.name


def sync_contact_mirror_fields(student: Any) -> bool:
	"""Copy the primary Contact's email and phone onto the hidden Student mirrors.

	Only non-empty Contact values overwrite the mirrors, so a Contact that has
	not been filled in yet cannot erase historical Student data.
	"""
	contact_name = (_get(student, "primary_contact") or "").strip()
	if not contact_name or not frappe.db.exists(CONTACT, contact_name):
		return False
	contact = frappe.get_doc(CONTACT, contact_name)
	email = get_contact_primary_email(contact)
	phone = get_contact_primary_phone(contact)

	changed = False
	if email and _get(student, EMAIL_MIRROR_FIELD) != email:
		_set(student, EMAIL_MIRROR_FIELD, email)
		changed = True
	if phone and _get(student, MOBILE_MIRROR_FIELD) != phone:
		_set(student, MOBILE_MIRROR_FIELD, phone)
		changed = True
	return changed


def get_student_primary_email(student: str) -> str:
	"""Return the primary Contact email, falling back to the legacy mirror."""
	primary_contact, legacy_email = frappe.db.get_value(
		STUDENT, student, ["primary_contact", EMAIL_MIRROR_FIELD]
	)
	if primary_contact:
		email = get_contact_primary_email(frappe.get_doc(CONTACT, primary_contact))
		if email:
			return email
	return (legacy_email or "").strip()


def get_student_primary_phone(student: str) -> str:
	"""Return the primary Contact phone, falling back to the legacy mirror."""
	primary_contact, legacy_mobile = frappe.db.get_value(
		STUDENT, student, ["primary_contact", MOBILE_MIRROR_FIELD]
	)
	if primary_contact:
		phone = get_contact_primary_phone(frappe.get_doc(CONTACT, primary_contact))
		if phone:
			return phone
	return (legacy_mobile or "").strip()


def get_student_by_email(email: str) -> str | None:
	"""Resolve a Student from a user email using the User link, mirror or Contact."""
	if not email:
		return None
	student = frappe.db.get_value(STUDENT, {"user": email}, "name")
	if student:
		return student
	student = frappe.db.get_value(STUDENT, {EMAIL_MIRROR_FIELD: email}, "name")
	if student:
		return student
	contact = frappe.db.get_value(CONTACT, {"email_id": email}, "name")
	if contact:
		return frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": CONTACT, "parent": contact, "link_doctype": STUDENT},
			"link_name",
		)
	return None


def update_linked_students_from_contact(contact, method=None) -> None:
	"""Keep Student mirror columns aligned when the primary Contact is edited."""
	if not contact or contact.doctype != CONTACT:
		return
	email = get_contact_primary_email(contact)
	phone = get_contact_primary_phone(contact)
	updates = {}
	if email:
		updates[EMAIL_MIRROR_FIELD] = email
	if phone:
		updates[MOBILE_MIRROR_FIELD] = phone
	if not updates:
		return
	for name in frappe.get_all(STUDENT, filters={"primary_contact": contact.name}, pluck="name"):
		frappe.db.set_value(STUDENT, name, updates, update_modified=False)
