from odoo import models, fields, api


class PurchaseRequisitionLine(models.Model):
    _inherit = "purchase.requisition.line"

    product_template_id = fields.Many2one(
        'product.template',
        string="Product Template",
        compute='_compute_product_template_id',
        inverse='_inverse_product_template_id',
        store=True,
        readonly=False,
        precompute=True,
        domain=[('purchase_ok', '=', True)],
    )

    is_configurable_product = fields.Boolean(
        related='product_template_id.has_configurable_attributes',
        depends=['product_template_id'],
    )

    product_template_attribute_value_ids = fields.Many2many(
        'product.template.attribute.value',
        related='product_id.product_template_attribute_value_ids',
        depends=['product_id'],
    )

    product_custom_attribute_value_ids = fields.One2many(
        'product.attribute.custom.value',
        'purchase_requisition_line_id',
        string="Custom Values",
        copy=True,
    )

    product_no_variant_attribute_value_ids = fields.Many2many(
        'product.template.attribute.value',
        relation='purchase_ext_conf_line_no_variant_ptav_rel',
        string="Extra Values",
        ondelete='restrict',
    )

    @api.depends('product_id')
    def _compute_product_template_id(self):
        for line in self:
            line.product_template_id = line.product_id.product_tmpl_id

    def _inverse_product_template_id(self):
        for line in self:
            if line.product_template_id and line.product_id.product_tmpl_id != line.product_template_id:
                line.product_id = False


class ProductAttributeCustomValue(models.Model):
    _inherit = "product.attribute.custom.value"

    purchase_requisition_line_id = fields.Many2one(
        'purchase.requisition.line',
        string="Purchase Requisition Line",
        ondelete='cascade',
    )
