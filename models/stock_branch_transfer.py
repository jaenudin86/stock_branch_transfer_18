from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    source_warehouse_id = fields.Many2one(
        'stock.warehouse', string='Gudang Asal'
    )
    destination_warehouse_id = fields.Many2one(
        'stock.warehouse', string='Gudang Tujuan'
    )
    transfer_type = fields.Selection([
        ('internal', 'Internal Transfer'),
        ('branch', 'Branch Transfer'),
    ], string='Tipe Transfer', default='branch')
    request_state = fields.Selection([
        ('draft', 'Draft'),
        ('requested', 'Requested'),
        ('approved', 'Approved'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status Request', default='draft', tracking=True)

    auto_create_pickings = fields.Boolean(
        string='Otomatis buat DO & Receipt saat Approve', default=True
    )

    def action_request(self):
        for rec in self:
            if rec.request_state != 'draft':
                continue
            rec.request_state = 'requested'

    def action_approve(self):
        for rec in self:
            if rec.request_state not in ('draft', 'requested'):
                continue
            # validasi minimal
            if not rec.source_warehouse_id or not rec.destination_warehouse_id:
                raise UserError(_("Gudang Asal dan Gudang Tujuan harus diisi sebelum approve."))
            rec.request_state = 'approved'

            # Jika user aktifkan auto_create_pickings -> buat pickings
            if rec.auto_create_pickings:
                rec._create_do_and_receipt()
    def action_done_request(self):
        """Mark transfer as done."""
        for rec in self:
            rec.transfer_state = 'done'
        return True
    def action_cancel_request(self):
        """Cancel the current branch transfer request"""
        for rec in self:
            rec.transfer_state = 'cancelled'
        return True
    def _get_internal_picking_type(self, warehouse):
        """Cari stock.picking.type dengan code 'internal' untuk warehouse; fallback jika tidak ada."""
        if not warehouse:
            return False
        p = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id)
        ], limit=1)
        if p:
            return p
        # fallback: ambil internal tanpa warehouse
        return self.env['stock.picking.type'].search([('code', '=', 'internal')], limit=1)

    def _create_do_and_receipt(self):
        """Buat dua picking: 1) DO di gudang asal, 2) Receipt di gudang tujuan.
           Keduanya memakai move yang sama (dihasilkan dari move_lines yang ada di record ini).
        """
        for rec in self:
            src_wh = rec.source_warehouse_id
            dst_wh = rec.destination_warehouse_id
            if not src_wh or not dst_wh:
                continue

            src_loc = src_wh.lot_stock_id       # lokasi gudang asal
            dst_loc = dst_wh.lot_stock_id       # lokasi gudang tujuan
            if not src_loc or not dst_loc:
                raise UserError(_("Lokasi gudang belum diset pada warehouse (lot_stock_id)."))

            # picking types
            ptype_src = self._get_internal_picking_type(src_wh)
            ptype_dst = self._get_internal_picking_type(dst_wh)

            origin = rec.name or _('BranchTransfer/%s') % (rec.id or '0')

            # Build move vals from current move_lines (jika ada), else dari move_lines planned
            move_template = []
            moves_source = rec.move_lines.filtered(lambda m: m.product_id)
            if not moves_source:
                # kalau tidak ada move di record (misal dibuat manual), abort gracefully
                raise UserError(_("Tidak ada Produk / Move lines pada transfer ini untuk dibuat DO/Receipt."))

            for m in moves_source:
                mv = {
                    'name': m.name or m.product_id.display_name,
                    'product_id': m.product_id.id,
                    'product_uom_qty': m.product_uom_qty,
                    'product_uom': m.product_uom.id,
                    'location_id': src_loc.id,
                    'location_dest_id': dst_loc.id,
                }
                move_template.append(mv)

            # Create Picking DO (source)
            picking_out_vals = {
                'picking_type_id': ptype_src.id if ptype_src else False,
                'location_id': src_loc.id,
                'location_dest_id': dst_loc.id,
                'partner_id': rec.partner_id.id or False,
                'origin': origin,
                'company_id': rec.company_id.id,
                'move_type': 'direct',
                'note': _('Auto-created DO for branch transfer %s') % origin,
            }
            picking_out = self.env['stock.picking'].create(picking_out_vals)

            # Create moves for picking_out
            move_obj = self.env['stock.move']
            for mv in move_template:
                mv_copy = mv.copy()
                mv_copy.update({
                    'picking_id': picking_out.id,
                })
                move_obj.create(mv_copy)

            # Create Picking Receipt (destination)
            picking_in_vals = {
                'picking_type_id': ptype_dst.id if ptype_dst else False,
                'location_id': src_loc.id,
                'location_dest_id': dst_loc.id,
                'partner_id': rec.partner_id.id or False,
                'origin': origin,
                'company_id': rec.company_id.id,
                'move_type': 'direct',
                'note': _('Auto-created Receipt for branch transfer %s') % origin,
            }
            picking_in = self.env['stock.picking'].create(picking_in_vals)

            for mv in move_template:
                mv_copy = mv.copy()
                mv_copy.update({
                    'picking_id': picking_in.id,
                })
                move_obj.create(mv_copy)

            # link group_id (optional) supaya picking saling terhubung di chatter
            # buat group stock.move.group
            group = self.env['procurement.group'].create({
                'name': origin,
            })
            picking_out.group_id = group
            picking_in.group_id = group

            # Update origin on original record so traceable
            if hasattr(rec, 'origin') and rec.origin:
                # leave existing origin
                pass
            else:
                rec.write({'origin': origin})

            # post message di chatter
            picking_out.message_post(body=_("DO otomatis dibuat dari request: %s") % origin)
            picking_in.message_post(body=_("Receipt otomatis dibuat dari request: %s") % origin)

            # optional: auto-confirm / auto-assign (jika ingin langsung ready)
            # picking_out.action_confirm()
            # picking_out.action_assign()
            # picking_in.action_confirm()
            # picking_in.action_assign()

