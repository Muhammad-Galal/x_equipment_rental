from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError

from .common import RentalCommon


class TestRentalWorkflow(RentalCommon):
    def test_confirm_requires_equipment_line(self):
        start_date = fields.Date.today() + timedelta(days=10)
        end_date = start_date + timedelta(days=2)
        order = self.env["x.rental.order"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "rental_start_date": start_date,
                "rental_end_date": end_date,
            }
        )

        with self.assertRaises(ValidationError):
            order.action_confirm()

    def test_invalid_transitions_are_blocked(self):
        start_date = fields.Date.today() + timedelta(days=15)
        end_date = start_date + timedelta(days=1)
        order = self._create_order(self.equipment_1, start_date, end_date)

        with self.assertRaises(UserError):
            order.action_mark_out()

        order.action_confirm()
        order.action_mark_out()

        with self.assertRaises(UserError):
            order.action_cancel()

    def test_happy_path_workflow(self):
        start_date = fields.Date.today() + timedelta(days=25)
        end_date = start_date + timedelta(days=2)
        order = self._create_order(self.equipment_1, start_date, end_date)

        order.action_confirm()
        self.assertEqual(order.state, "confirmed")
        self.assertTrue(order.sale_order_id)

        order.action_mark_out()
        self.assertEqual(order.state, "out")

        order.action_return()
        self.assertEqual(order.state, "returned")
        self.assertEqual(order.actual_return_date, fields.Date.today())

        order.action_mark_invoiced()
        self.assertEqual(order.state, "invoiced")
