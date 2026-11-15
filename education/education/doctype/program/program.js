// Copyright (c) 2015, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Program', {
  setup: function (frm) {
    frm.set_query('course', 'courses', function (doc, cdt, cdn) {
      let added = (doc.courses || [])
        .filter((row) => row.name !== cdn && row.course)
        .map((row) => row.course)

      if (!added.length) return {}

      return {
        filters: {
          name: ['not in', added],
        },
      }
    })
  },
  refresh: function (frm) {
    frm.trigger('set_filters')
  },
  company: function (frm) {
    frm.trigger('set_filters')
  },

  set_filters(frm) {
    if (frm.doc.company) {
      frm.set_query('department', function () {
        return {
          filters: {
            company: frm.doc.company,
            disabled: 0,
          },
        }
      })
    }
  },
})
