from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def get_variant_by_reference(self, reference):
        """Resolve a typed internal reference to a single product.product variant.

        Internal references are generated per product.category with a
        category-specific letter prefix (product_sequence's
        product.category.code_prefix, e.g. 'T03-0071', 'F01-0001'). Users
        sometimes drop that prefix for speed, so if the typed text doesn't
        match a code exactly, also try it as a suffix of the real code.
        """
        self.ensure_one()
        reference = (reference or "").strip()
        if not reference:
            return {}
        Product = self.env["product.product"]
        domain = [("product_tmpl_id", "=", self.id)]
        variant = Product.search(domain + [("default_code", "=", reference)], limit=2)
        if not variant:
            variant = Product.search(domain + [("default_code", "=ilike", "%" + reference)], limit=2)
        if len(variant) == 1:
            return {"product_id": variant.id, "product_name": variant.display_name}
        return {}
