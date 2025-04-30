from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from odoo import _

class RmaStage(models.Model):
    _name = 'rma.stage'
    _description = 'RMA Stage'
    _order = 'sequence'

    name = fields.Char(string='Stage Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string='Folded in Kanban')
    description = fields.Text(translate=True)
    template_id = fields.Many2one('mail.template', string='Email Template')
    sms_template_id = fields.Many2one('sms.template', string='SMS Template')

class RmaTag(models.Model):
    _name = 'rma.tag'
    _description = 'RMA Tag'

    name = fields.Char(string='Tag Name', required=True)
    color = fields.Integer(string='Color Index')

class CustomRma(models.Model):
    _name = 'custom.rma'
    _description = 'Custom RMA'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    active = fields.Boolean(default=True, string='Active')
    name = fields.Char(required=True, tracking=True)
    customer_id = fields.Many2one('res.partner', string='Customer', required=True)
    phone = fields.Char(related='customer_id.phone')
    email = fields.Char(related='customer_id.email')
    invoice_id = fields.Many2one('account.move', string='Invoices', domain="[('move_type','=','out_invoice')]")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    date = fields.Date(string='Date', default=fields.Date.context_today, tracking=True)
    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    reason = fields.Selection([
        ('picking_error', 'Picking Error'),
        ('customer_order_error', 'Customer Order Error'),
        ('order_delivered', 'Order Delivered'),
    ], string="Reason", tracking=True)
    state = fields.Selection([
        ('normal', 'In Progress'),
        ('done', 'Ready'),
        ('blocked', 'Blocked')
    ], string="Status", default='normal', tracking=True)

    rma_line_ids = fields.One2many('custom.rma.line', 'rma_id', string='RMA Lines')
    product_id = fields.Many2one('product.product', string='Product', compute='_compute_product_id', store=True)
    invoiced_qty = fields.Float(string='Invoiced Qty', compute='_compute_quantities', store=True)
    returned_qty = fields.Float(string='Returned Qty', compute='_compute_quantities', store=True)
    unit_price = fields.Float(string='Unit Price', compute='_compute_unit_price', store=True)
    total = fields.Float(string='Total', compute='_compute_total', store=True)
    stage_id = fields.Many2one('rma.stage', 
        string='Stage', 
        tracking=True,
        group_expand='_read_group_stage_ids',
        default=lambda self: self.env['rma.stage'].search([], limit=1, order='sequence'))
    tag_ids = fields.Many2many('rma.tag', string='Tags')
    priority = fields.Boolean(string='High Priority', default=False)
    partner_latitude = fields.Float(string='Latitude', related='customer_id.partner_latitude', store=True)
    partner_longitude = fields.Float(string='Longitude', related='customer_id.partner_longitude', store=True)
    picking_id = fields.Many2one('stock.picking', string='Internal Transfer', tracking=True)
    credit_note_id = fields.Many2one('account.move', string='Credit Note', tracking=True)

    @api.depends('rma_line_ids.product_id')
    def _compute_product_id(self):
        for record in self:
            record.product_id = record.rma_line_ids[0].product_id if record.rma_line_ids else False

    @api.depends('rma_line_ids.invoiced_qty', 'rma_line_ids.returned_qty')
    def _compute_quantities(self):
        for record in self:
            record.invoiced_qty = sum(record.rma_line_ids.mapped('invoiced_qty'))
            record.returned_qty = sum(record.rma_line_ids.mapped('returned_qty'))

    @api.depends('rma_line_ids.unit_price')
    def _compute_unit_price(self):
        for record in self:
            if record.rma_line_ids:
                record.unit_price = record.rma_line_ids[0].unit_price
            else:
                record.unit_price = 0.0

    @api.depends('rma_line_ids.total')
    def _compute_total(self):
        for record in self:
            record.total = sum(record.rma_line_ids.mapped('total'))

    @api.onchange('invoice_id')
    def _onchange_invoice_id(self):
        if self.invoice_id:
            lines = []
            for inv_line in self.invoice_id.invoice_line_ids:
                if inv_line.product_id and inv_line.quantity > 0:
                    lines.append((0, 0, {
                        'product_id': inv_line.product_id.id,
                        'invoiced_qty': inv_line.quantity,
                        'unit_price': inv_line.price_unit,
                        'returned_qty': 0.0,
                    }))
            self.rma_line_ids = False  # Clear existing lines
            self.rma_line_ids = lines
        else:
            self.rma_line_ids = False

    def write(self, vals):
        if 'stage_id' in vals:
            new_stage = self.env['rma.stage'].browse(vals['stage_id'])
            for record in self:
                if record.stage_id.id == self.env.ref('custom_rma.stage_awaiting_stock').id:
                    if new_stage.id == self.env.ref('custom_rma.stage_awaiting_credit').id:
                        raise ValidationError(_('You cannot move an RMA directly from Awaiting Stock Receipt to Awaiting Credit Note stage.'))
        if 'state' in vals:
            vals['state'] = vals['state']
        return super(CustomRma, self).write(vals)

    @api.model
    def _read_group_stage_ids(self, stages=None, domain=None, order=None):
        """ Read all the stages and display them in the kanban view,
            even if they are empty """
        return self.env['rma.stage'].search([], order='sequence')

    def action_create_transfer(self):
        pass
        # for rma in self:
        #     if not rma.rma_line_ids:
        #         raise UserError(_('Cannot create transfer without RMA lines.'))
            
        #     picking_type = self.env['stock.picking.type'].search([
        #         ('code', '=', 'internal')
        #     ], limit=1)

        #     vals = {
        #         'picking_type_id': picking_type.id,
        #         'location_id': picking_type.default_location_src_id.id,
        #         'location_dest_id': picking_type.default_location_dest_id.id,
        #         'origin': rma.name,
        #     }
        #     picking = self.env['stock.picking'].create(vals)
            
        #     for line in rma.rma_line_ids:
        #         self.env['stock.move'].create({
        #             'name': line.product_id.name,
        #             'product_id': line.product_id.id,
        #             'product_uom_qty': line.returned_qty,
        #             'product_uom': line.product_id.uom_id.id,
        #             'picking_id': picking.id,
        #             'location_id': picking_type.default_location_src_id.id,
        #             'location_dest_id': picking_type.default_location_dest_id.id,
        #         })
            
        #     rma.picking_id = picking.id
        #     rma.message_post(body=_("Internal transfer %s created") % picking.name)
        #     return self._get_stock_picking_action(picking)

    def action_validate_transfer(self):
        pass
        # for rma in self:
        #     if not rma.picking_id:
        #         raise UserError(_('No transfer to validate.'))
        #     if rma.picking_id.state != 'assigned':
        #         raise UserError(_('Transfer must be ready to validate.'))
            
        #     rma.picking_id.button_validate()
        #     if rma.stage_id == self.env.ref('custom_rma.stage_awaiting_stock'):
        #         next_stage = self.env.ref('custom_rma.stage_awaiting_credit')
        #         rma.write({'stage_id': next_stage.id})
            
        #     rma.message_post(body=_("Internal transfer %s validated") % rma.picking_id.name)

    def action_create_credit_note(self):
        for rma in self:
            if not rma.invoice_id:
                raise UserError(_('Cannot create credit note without original invoice.'))
            
            credit_note = rma.invoice_id._reverse_moves(
                default_values_list=[{
                    'ref': _('Credit Note for %s') % rma.name,
                }]
            )
            rma.credit_note_id = credit_note.id
            if rma.stage_id == self.env.ref('custom_rma.stage_awaiting_credit'):
                next_stage = self.env.ref('custom_rma.stage_closed')
                rma.write({'stage_id': next_stage.id})
            
            rma.message_post(body=_("Credit note %s created") % credit_note.name)
            return self._get_credit_note_action(credit_note)

    def _get_stock_picking_action(self, picking):
        return {
            'name': _('Internal Transfer'),
            'view_mode': 'form',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'type': 'ir.actions.act_window',
        }

    def _get_credit_note_action(self, credit_note):
        return {
            'name': _('Credit Note'),
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': credit_note.id,
            'type': 'ir.actions.act_window',
        }

class CustomRmaLine(models.Model):
    _name = 'custom.rma.line'
    _description = 'RMA Line'

    rma_id = fields.Many2one('custom.rma', 
        string='RMA Reference', 
        ondelete='cascade',
        required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    invoiced_qty = fields.Float(string='Invoiced Qty')
    returned_qty = fields.Float(string='Returned Qty')
    unit_price = fields.Float(string='Unit Price')
    total = fields.Float(string='Total', compute='_compute_total', store=True)

    @api.depends('returned_qty', 'unit_price')
    def _compute_total(self):
        for line in self:
            line.total = line.returned_qty * line.unit_price