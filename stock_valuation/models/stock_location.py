# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"


    def _should_be_valued(self):
            """ This method returns a boolean reflecting whether the products stored in `self` should
            be considered when valuating the stock of a company.
            """
            self.ensure_one()
            if self.usage == 'internal':
                return True
            return False
    
    