import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class FinancialStatementTable(models.Model):
    _name = 'financial.statement.table'
    _sql_constraints = [('name', 'unique(name)',
                         "Le nom doit etre unique, vérifiez que ce nom n'est pas utilisé par un autre tableau!"),
                        ('code', 'unique(code)',
                         "Le code doit etre unique, vérifiez que ce code n'est pas utilisé par un autre tableau!")]

    name = fields.Char(string="Nom du tableau")
    code = fields.Char(string="Code")
    heading_ids = fields.One2many('financial.statement.heading', 'table_id', string='Rubriques',
                                  domain=[('parent_id', '=', False)])


class FinancialStatementHeading(models.Model):
    _name = 'financial.statement.heading'
    _description = 'Rubriques'

    def _get_heading_account_lines(self):
        return [('company_id', '=', self.env.user.company_id.id)]

    name = fields.Char(string="Libelle", required=True)
    ref = fields.Char(string="Reférence")
    other = fields.Char(string="Formule")
    sequence = fields.Integer(string="Ordre d'affichage")
    parent_id = fields.Many2one('financial.statement.heading', string='Rubrique parent', index=True)
    child_ids = fields.One2many('financial.statement.heading', 'parent_id', string='Rubriques', readonly=True)
    table_id = fields.Many2one('financial.statement.table', string='Type de tableau', index=True, readonly=True)
    color = fields.Integer('Color Index')
    heading_account_line_ids = fields.One2many('financial.rel.heading.account', 'heading_id',
                                               string='Lignes de comptes',
                                               readonly=False)


class FinancialHeadingAccount(models.Model):
    _name = "financial.rel.heading.account"

    heading_id = fields.Many2one('financial.statement.heading', string='Rubrique', index=True)
    input_account = fields.Char("Comptes", help="Comptes")
    except_account = fields.Char("Comptes à exclure", help="Comptes à exclure")
    fiscal_period = fields.Selection([('n', 'N'), ('n_1', 'N-1'), ('n_n_1', 'N et N-1'), ('n_1_n_2', 'N-1 et N-2')], default='n')
    column_input = fields.Selection([('', ''), ('gross', 'Brut'), ('amortization', 'Amortissements/dépréciations')])
    sign = fields.Integer("Sign", default=1)
    operation = fields.Selection(
        [
            ('sum_movement_credit', '∑(Mouvement crédit)'),
            ('sum_movement_debit', '∑(Mouvement débit)'),
            ('sum_debit', '∑(Solde débiteur)'),
            ('sum_credit', '∑(Solde crediteur)'),
            ('sum_balance_credit', '∑(Balance crédit)'),
            ('sum_balance_debit', '∑(Balance débit)'),
            ('fiscal_year', '∑(Année fiscale)')],
        default="balance_credit",
        help="""
         Opérations disponibles
         1) Mouvement Debit = ∑(Mouvement de la colonne debit)
         2) Mouvement Credit = ∑(Mouvement de la colonne credit)
         3) Solde Débiteur = ∑(Solde Debiteur)
         4) Solde Crediteur = ∑(Solde Crediteur)
         5) Balance credit = ∑(Balance credit)
         6) Balance debit = ∑(Balance debit)
         """)
