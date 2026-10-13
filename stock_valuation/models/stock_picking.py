# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright 2026 Yaser Akhras
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models, _, fields 



class Picking(models.Model):
    _inherit = "stock.picking"

    result = fields.Text('Result')

    destination = fields.Many2one(
        string='Destination',
        comodel_name='stock.location',
        ondelete='restrict',
        domain=[('usage', '=', 'internal')],
    )

    sequence_code = fields.Char(
        related='picking_type_id.sequence_code',
        store=True
    )
    
    

    def button_validate(self):
        res = super().button_validate()
        self._create_exo_transfer()
        # self.result = self.env.context
        return res
        

    def _create_exo_transfer(self):
        """Create EXI picking when EXO transfer is done"""
        if self.picking_type_id.sequence_code == 'EXO' and self.state == 'done':
            exi_type = self.env['stock.picking.type'].search([
                ('sequence_code', '=', 'EXI')
            ], limit=1)
            
            new_picking = self.env['stock.picking'].create({
                'origin': self.name,
                'picking_type_id': exi_type.id,
                'location_id': self.location_dest_id.id,
                'location_dest_id': self.destination.id,
            })
            
            # Copy all move lines
            for move in self.move_ids_without_package:
                move.copy({
                    'picking_id': new_picking.id,
                    'location_id': self.location_dest_id.id,
                    'location_dest_id': self.destination.id,
                    'origin_returned_move_id': move.id,
                })
            
            return new_picking
        return False
