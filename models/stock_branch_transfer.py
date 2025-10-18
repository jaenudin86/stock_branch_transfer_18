from odoo import models, fields, api
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    transfer_type = fields.Selection(
        selection=[('branch', 'Branch Transfer'), ('internal', 'Internal')],
        string='Transfer Type',
        default='branch'
    )

    transfer_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('requested', 'Requested'),
            ('in_transit', 'In Transit'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Transfer State',
        default='draft',
        tracking=True
    )

    warehouse_from_id = fields.Many2one('stock.warehouse', string='Gudang Asal', readonly=True)
    warehouse_to_id = fields.Many2one('stock.warehouse', string='Gudang Tujuan')
    request_note = fields.Text(string='Alasan / Catatan Permintaan')

    source_location_id = fields.Many2one('stock.location', string='Lokasi Sumber (pengirim)')
    dest_location_id = fields.Many2one('stock.location', string='Lokasi Tujuan (penerima)')

    picking_request_id = fields.Many2one('stock.picking', string='Related Picking')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # default warehouse_from_id based on user's company -> pick first warehouse
        if not res.get('warehouse_from_id'):
            user = self.env.user
            wh = self.env['stock.warehouse'].search([('company_id', '=', user.company_id.id)], limit=1)
            if wh:
                res['warehouse_from_id'] = wh.id
        return res

    def action_submit_request(self):
        # Submit request to warehouse_to (becomes requested)
        for rec in self:
            if not rec.warehouse_to_id:
                raise UserError('Pilih Gudang Tujuan sebelum submit request.')
            rec.transfer_state = 'requested'

    def action_send_goods(self):
        # Warehouse_to prepares and sends goods -> create outbound picking and validate (stock reduced)
        for rec in self:
            if rec.transfer_state != 'requested':
                raise UserError('Request harus berada di state "requested" untuk dikirim.')
            if not rec.source_location_id:
                raise UserError('Pilih Lokasi Sumber di gudang pengirim terlebih dahulu.')
            # create picking out from warehouse_to
            Picking = self.env['stock.picking']
            move_vals = []
            for m in rec.move_lines:
                # If no moves (move_lines empty), fallback to move_ids_without_package creation using request's move lines (if any)
                pass
            # create picking with move lines from stock.move lines of current picking if exists,
            # otherwise use move_lines from the current record's stock.move (in case of inherited)
            # We will collect product lines from the existing stock.move in request (if any),
            # otherwise try to read from move_lines (which is typical for stock.picking).
            product_moves = []
            if rec.move_lines:
                for mv in rec.move_lines:
                    product_moves.append((0,0,{
                        'name': mv.name or mv.product_id.display_name,
                        'product_id': mv.product_id.id,
                        'product_uom': mv.product_uom.id,
                        'product_uom_qty': mv.product_uom_qty,
                        'location_id': rec.source_location_id.id,
                        'location_dest_id': rec.warehouse_from_id.wh_transit_loc_id.id if hasattr(rec.warehouse_from_id, 'wh_transit_loc_id') else rec.warehouse_from_id.lot_stock_id.id,
                    }))
            else:
                # fallback: if there are no move_lines, try to create moves from request's origin moves (if any)
                raise UserError('Tidak ada product lines yang dapat dikirim. Pastikan request memiliki product lines.')
            picking_vals = {
                'picking_type_id': rec.warehouse_to_id.out_type_id.id,
                'location_id': rec.source_location_id.id,
                'location_dest_id': rec.warehouse_from_id.wh_transit_loc_id.id if hasattr(rec.warehouse_from_id, 'wh_transit_loc_id') else rec.warehouse_from_id.lot_stock_id.id,
                'origin': rec.name or rec.origin or False,
                'move_ids_without_package': product_moves,
            }
            picking = Picking.create(picking_vals)
            rec.picking_request_id = picking
            picking.action_confirm()
            picking.action_assign()
            picking.button_validate()
            rec.transfer_state = 'in_transit'

    def action_receive_goods(self):
        # Warehouse_from receives goods -> create incoming picking into destination location and validate
        for rec in self:
            if rec.transfer_state != 'in_transit':
                raise UserError('Request harus berada di state "in_transit" untuk diterima.')
            if not rec.dest_location_id:
                raise UserError('Pilih Lokasi Tujuan penerimaan di gudang penerima.')
            Picking = self.env['stock.picking']
            product_moves = []
            # use the recorded picking to build incoming, or use move lines
            if rec.picking_request_id and rec.picking_request_id.move_lines:
                for mv in rec.picking_request_id.move_lines:
                    product_moves.append((0,0,{
                        'name': mv.name or mv.product_id.display_name,
                        'product_id': mv.product_id.id,
                        'product_uom': mv.product_uom.id,
                        'product_uom_qty': mv.product_uom_qty,
                        'location_id': mv.location_dest_id.id,
                        'location_dest_id': rec.dest_location_id.id,
                    }))
            else:
                raise UserError('Tidak ada picking pengiriman yang ditemukan untuk membuat penerimaan.')
            picking_vals = {
                'picking_type_id': rec.warehouse_from_id.in_type_id.id,
                'location_id': rec.warehouse_to_id.lot_stock_id.id,
                'location_dest_id': rec.dest_location_id.id,
                'origin': rec.name or False,
                'move_ids_without_package': product_moves,
            }
            picking_in = Picking.create(picking_vals)
            picking_in.action_confirm()
            picking_in.action_assign()
            picking_in.button_validate()
            rec.transfer_state = 'done'

