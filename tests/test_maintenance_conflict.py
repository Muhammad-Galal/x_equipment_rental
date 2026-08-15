from datetime import datetime, time, timedelta

from odoo import fields
from odoo.exceptions import ValidationError

from .common import RentalCommon


class TestMaintenanceConflict(RentalCommon):
    def test_rental_confirmation_blocked_by_maintenance(self):
        start_date = fields.Date.today() + timedelta(days=12)
        end_date = start_date + timedelta(days=1)
        self.env["maintenance.request"].create(
            {
                "name": "Excavator service window",
                "equipment_id": self.equipment_1.id,
                "maintenance_team_id": self.team.id,
                "company_id": self.company.id,
                "schedule_date": fields.Datetime.to_string(datetime.combine(start_date, time(9, 0))),
                "schedule_end": fields.Datetime.to_string(datetime.combine(end_date, time(18, 0))),
            }
        )
        order = self._create_order(self.equipment_1, start_date, end_date)

        with self.assertRaises(ValidationError):
            order.action_confirm()

    def test_maintenance_creation_blocked_by_confirmed_rental(self):
        start_date = fields.Date.today() + timedelta(days=18)
        end_date = start_date + timedelta(days=2)
        order = self._create_order(self.equipment_1, start_date, end_date)
        order.action_confirm()

        with self.assertRaises(ValidationError):
            self.env["maintenance.request"].create(
                {
                    "name": "Overlapping maintenance",
                    "equipment_id": self.equipment_1.id,
                    "maintenance_team_id": self.team.id,
                    "company_id": self.company.id,
                    "schedule_date": fields.Datetime.to_string(datetime.combine(start_date, time(8, 0))),
                    "schedule_end": fields.Datetime.to_string(datetime.combine(end_date, time(17, 0))),
                }
            )
