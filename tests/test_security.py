from datetime import timedelta

from odoo import fields

from .common import RentalCommon


class TestRentalSecurity(RentalCommon):
    def test_rental_user_only_sees_own_orders(self):
        start_date = fields.Date.today() + timedelta(days=40)
        end_date = start_date + timedelta(days=1)
        own_order = self._create_order(
            self.equipment_1,
            start_date,
            end_date,
            user_id=self.rental_user.id,
        )
        other_order = self._create_order(
            self.equipment_2,
            start_date + timedelta(days=3),
            end_date + timedelta(days=3),
            user_id=self.rental_manager.id,
        )

        own_visible_orders = self.env["x.rental.order"].with_user(self.rental_user).search([])
        manager_visible_orders = self.env["x.rental.order"].with_user(self.rental_manager).search([])

        self.assertIn(own_order, own_visible_orders)
        self.assertNotIn(other_order, own_visible_orders)
        self.assertIn(own_order, manager_visible_orders)
        self.assertIn(other_order, manager_visible_orders)
