from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    rental_sale_integration_mode = fields.Selection(
        [
            ("sale_order", "Sales Order"),
            ("customer_invoice", "Customer Invoice"),
        ],
        string="Rental Sales Integration",
        default="sale_order",
        required=True,
        config_parameter="x_equipment_rental.rental_sale_integration_mode",
    )
    rental_service_product_id = fields.Many2one(
        "product.product",
        string="Rental Service Product",
        domain="[('sale_ok', '=', True), ('type', '=', 'service')]",
        config_parameter="x_equipment_rental.rental_service_product_id",
    )
    rental_late_fee_per_day = fields.Float(
        string="Late Fee Per Day",
        config_parameter="x_equipment_rental.rental_late_fee_per_day",
        help="Fixed late fee charged per overdue day and per rented equipment line.",
    )
