# -*- coding: utf-8 -*-
import logging

from odoo import fields, models, api

_logger = logging.getLogger(__name__)


class HeadingRelAccount(models.TransientModel):
    _name = "financial.rel.heading.account.wizard"

    @api.model
    def _get_account_eligible(self):
        heading = self.env["financial.statement.heading"].search(
            [('id', '=', self.env.context.get('default_heading_id'))])
        return [('id', 'not in', [a.account_id.id for a in heading.heading_account_line_ids])]

    heading_id = fields.Many2one('financial.statement.heading', string='Rubrique', default=lambda s: s._get_heading())
    account_ids = fields.Many2many('account.account', 'heading_account_wizard_rel', string='Comptes',
                                   domain=lambda self: self._get_account_eligible())
    type = fields.Selection([('', ''), ('gross', 'Brut'), ('amortization', 'Amortissements/dépréciations')])
    operation = fields.Selection(
        [('balance_debit', '∑(Debit -  Credit)'),
         ('balance_credit', '∑(Credit -  Debit)'),
         ('sum_debit', '∑(Solde Debiteur)'),
         ('sum_credit', '∑(Solde crediteur)'),
         ('sum_movement_credit', '∑(Mouvement credit)'),
         ('sum_movement_debit', '∑(Mouvement debit)'),
         ('fiscal_year', '∑(Année fiscale)')],
        default="balance_credit",
        help="""
            Opérations disponibles
            1) Balance Débit = ∑(Debit - Credit)
            2) Balance Credit = ∑(Credit - Debit)
            3) Solde Débiteur = ∑(Solde Debiteur)
            4) Solde Crediteur = ∑(Solde Crediteur)
            5) Mouvement Debit = ∑(Mouvement debit)
            6) Mouvement Credit = ∑(Mouvement Credit)
            """)

    def _get_heading(self):
        return self.env['financial.statement.heading'].search(
            [('id', '=', self.env.context.get('default_heading_id'))])[0]

    @api.multi
    def save(self):
        for account in self.account_ids:
            self.env['financial.rel.heading.account'].create(
                {'heading_id': self.heading_id.id, 'account_id': account.id, 'type': self.type,
                 'operation': self.operation})
        return True
