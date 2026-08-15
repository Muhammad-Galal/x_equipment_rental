from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RentalAvailabilityWizard(models.TransientModel):
    _name = "x.rental.availability.wizard"
    _description = "Rental Availability Wizard"

    start_date = fields.Date(required=True, default=fields.Date.context_today)
    end_date = fields.Date(required=True, default=fields.Date.context_today)
    category_id = fields.Many2one("maintenance.equipment.category", string="Equipment Category")
    available_equipment_count = fields.Integer(
        compute="_compute_available_equipment_count",
        string="Available Equipment",
    )

    @api.depends("start_date", "end_date", "category_id")
    def _compute_available_equipment_count(self):
        equipment_model = self.env["maintenance.equipment"]
        for wizard in self:
            if not wizard.start_date or not wizard.end_date or wizard.end_date < wizard.start_date:
                wizard.available_equipment_count = 0
                continue
            wizard.available_equipment_count = equipment_model.search_count(
                wizard._get_available_equipment_domain()
            )

    def _get_available_equipment_domain(self):
        self.ensure_one()
        unavailable_ids = self.env["maintenance.equipment"]._get_unavailable_equipment_ids(
            self.start_date,
            self.end_date,
            company_id=self.env.company.id,
        )
        domain = [("id", "not in", unavailable_ids)]
        if self.category_id:
            domain.append(("category_id", "=", self.category_id.id))
        return domain

    @api.constrains("start_date", "end_date")
    def _check_date_range(self):
        for wizard in self:
            if wizard.start_date and wizard.end_date and wizard.end_date < wizard.start_date:
                raise ValidationError(_("The availability end date must be on or after the start date."))

    def action_show_available_equipment(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("x_equipment_rental.action_rental_equipment")
        action["domain"] = self._get_available_equipment_domain()
        action["context"] = {
            "search_default_filter_available_now": 0,
            "default_category_id": self.category_id.id,
        }
        action["name"] = _(
            "Available Equipment (%(start)s to %(end)s)",
            start=self.start_date,
            end=self.end_date,
        )
        return action
