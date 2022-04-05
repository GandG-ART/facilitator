import copy
import datetime
import logging

from collections import defaultdict
from math import copysign
from datetime import datetime
from babel.dates import get_quarter_names
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.tools import date_utils
from odoo.tools.misc import formatLang, format_date, DEFAULT_SERVER_DATE_FORMAT

_logger = logging.getLogger(__name__)


class CashFlowTable(models.AbstractModel):
    _name = 'financial.statement.cash.flow.table'
    _description = 'Tableau de flux de trésorerie'

    filter_date = {'date_from': '', 'date_to': '', 'mode': 'range', 'filter': 'this_year'}
    period_size = {'this_year': 2}
    items = {}

    ####################################################
    # OPTIONS: CORE
    ####################################################

    @api.model
    def _get_options(self, previous_options=None):
        # Create default options.
        options = {}
        if self.filter_date:
            self._init_filter_date(options, previous_options=previous_options)
        return options

    @api.model
    def _init_filter_date(self, options, previous_options=None):
        if self.filter_date is None:
            return

        # Default values.
        mode = self.filter_date.get('mode', 'range')
        options_filter = self.filter_date.get('filter') or ('today' if mode == 'single' else 'fiscalyear')
        date_from = self.filter_date.get('date_from') and fields.Date.from_string(self.filter_date['date_from'])
        date_to = self.filter_date.get('date_to') and fields.Date.from_string(self.filter_date['date_to'])
        # Handle previous_options.
        if previous_options and previous_options.get('date') and previous_options['date'].get('filter') \
                and not (previous_options['date']['filter'] == 'today' and mode == 'range'):

            options_filter = previous_options['date']['filter']
            if options_filter == 'custom':
                if previous_options['date']['date_from'] and mode == 'range':
                    date_from = fields.Date.from_string(previous_options['date']['date_from'])
                if previous_options['date']['date_to']:
                    date_to = fields.Date.from_string(previous_options['date']['date_to'])

        # Create date option for each company.
        period_type = False
        if 'year' in options_filter:
            company_fiscalyear_dates = self.env.user.company_id.compute_fiscalyear_dates(
                fields.Date.context_today(self))
            date_from = company_fiscalyear_dates['date_from']
            date_to = company_fiscalyear_dates['date_to']
        elif not date_from:
            # options_filter == 'custom' && mode == 'single'
            date_from = date_utils.get_month(date_to)[0]

        options['date'] = self._get_dates_period(options, date_from, date_to, mode, period_type=period_type)
        options['date']['filter'] = options_filter

    @api.model
    def _get_dates_period(self, options, date_from, date_to, mode, period_type=None):
        '''Compute some information about the period:
        * The name to display on the report.
        * The period type (e.g. quarter) if not specified explicitly.
        :param date_from:   The starting date of the period.
        :param date_to:     The ending date of the period.
        :param period_type: The type of the interval date_from -> date_to.
        :return:            A dictionary containing:
            * date_from * date_to * string * period_type * mode *
        '''

        def match(dt_from, dt_to):
            return (dt_from, dt_to) == (date_from, date_to)

        string = None
        # If no date_from or not date_to, we are unable to determine a period
        if not period_type or period_type == 'custom':
            date = date_to or date_from
            company_fiscalyear_dates = self.env.user.company_id.compute_fiscalyear_dates(date)
            if match(company_fiscalyear_dates['date_from'], company_fiscalyear_dates['date_to']):
                period_type = 'fiscalyear'
                if company_fiscalyear_dates.get('record'):
                    string = company_fiscalyear_dates['record'].name
            elif match(*date_utils.get_quarter(date)):
                period_type = 'quarter'
            elif match(*date_utils.get_fiscal_year(date)):
                period_type = 'year'
            else:
                period_type = 'custom'
        elif period_type == 'fiscalyear':
            date = date_to or date_from
            company_fiscalyear_dates = self.env.user.company_id.compute_fiscalyear_dates(date)
            record = company_fiscalyear_dates.get('record')
            string = record and record.name

        if not string:
            fy_day = self.env.user.company_id.fiscalyear_last_day
            fy_month = int(self.env.user.company_id.fiscalyear_last_month)
            if mode == 'single':
                string = _('As of %s') % (format_date(self.env, fields.Date.to_string(date_to)))
            elif period_type == 'year' or (
                    period_type == 'fiscalyear' and (date_from, date_to) == date_utils.get_fiscal_year(date_to)):
                string = date_to.strftime('%Y')
            elif period_type == 'fiscalyear' and (date_from, date_to) == date_utils.get_fiscal_year(date_to, day=fy_day,
                                                                                                    month=fy_month):
                string = '%s - %s' % (date_to.year - 1, date_to.year)
            else:
                dt_from_str = format_date(self.env, fields.Date.to_string(date_from))
                dt_to_str = format_date(self.env, fields.Date.to_string(date_to))
                string = _('From %s\nto  %s') % (dt_from_str, dt_to_str)

        return {
            'string': string,
            'period_type': period_type,
            'mode': mode,
            'date_from': date_from and fields.Date.to_string(date_from) or False,
            'date_to': fields.Date.to_string(date_to),
            'show_quarter': False,
        }

    ####################################################
    # QUERIES
    ####################################################

    @api.model
    def _get_query_currency_table(self, options):
        ''' Construct the currency table as a mapping company -> rate to convert the amount to the user's company
        currency in a multi-company/multi-currency environment.
        The currency_table is a small postgresql table construct with VALUES.
        :param options: The report options.
        :return:        The query representing the currency table.
        '''

        user_company = self.env.user.company_id
        user_currency = user_company.currency_id
        if options.get('multi_company'):
            company_ids = [c['id'] for c in self._get_options_companies(options) if
                           c['id'] != user_company.id and c['selected']]
            company_ids.append(self.env.user.company_id.id)
            companies = self.env['res.company'].browse(company_ids)
            conversion_date = options['date']['date_to']
            currency_rates = companies.mapped('currency_id')._get_rates(user_company, conversion_date)
        else:
            companies = user_company
            currency_rates = {user_currency.id: 1.0}

        conversion_rates = []
        for company in companies:
            conversion_rates.append((
                company.id,
                currency_rates[user_company.currency_id.id] / currency_rates[company.currency_id.id],
                user_currency.decimal_places,
            ))

        currency_table = ','.join('(%s, %s, %s)' % args for args in conversion_rates)
        return '(VALUES %s) AS currency_table(company_id, rate, precision)' % currency_table

    ####################################################
    # MISC
    ####################################################

    def get_header(self, options):
        columns = self._get_columns_name(options)
        return [columns]

    # TO BE OVERWRITTEN
    def _get_columns_name_hierarchy(self, options):
        return []

    # TO BE OVERWRITTEN
    def _get_columns_name(self, options):
        columns = [
            {'name': 'Ref', 'class': 'number'},
            {'name': _('Libelle')},
        ]
        date_option = options.get('date')
        return columns + self.get_heading_items_header(date_option)

    def get_heading_items_header(self, date_options):
        fiscal_year = self.env.user.company_id.compute_fiscalyear_dates(
            datetime.strptime(date_options.get('date_from'), '%Y-%m-%d').date())
        date_from, date_to = fiscal_year['date_from'], fiscal_year['date_to']
        date_previous = date_to - relativedelta(years=1)
        columns = []
        if 'this_year' == date_options.get('filter') or date_options.get('filter') == 'custom':
            columns = [{'name': _('Exercice N (%s)' % date_to.year), 'class': 'number table_parent'},
                       {'name': _('Exercice N-1 (%s)' % date_previous.year), 'class': 'number table_parent'}]
        return columns

    def _get_period_name(self, date_from):
        string = None
        if self.filter_period == 'annual':
            string = date_from.strftime('%Y')
        return string

    def _get_templates(self):
        return {
            'main_template': 'financial_statement_reporting.main_template',
            'main_table_header_template': 'financial_statement_reporting.main_table_header',
            'line_template': 'financial_statement_reporting.line_template',
            'footnotes_template': 'financial_statement_reporting.footnotes_template',
            'search_template': 'financial_statement_reporting.search_template',
        }

    # TO BE OVERWRITTEN
    def _get_report_name(self):
        return _('Tableau de flux de trésorerie')

    def _set_context(self, options):
        """This method will set information inside the context based on the options dict as some options need to be in context for the query_get method defined in account_move_line"""
        ctx = self.env.context.copy()
        if options.get('date') and options['date'].get('date_from'):
            ctx['date_from'] = options['date']['date_from']
        if options.get('date'):
            ctx['date_to'] = options['date'].get('date_to') or options['date'].get('date')
        return ctx

    def get_report_informations(self, options):
        '''
        return a dictionary of informations that will be needed by the js widget, manager_id, footnotes, html of report and searchview, ...
        '''
        self.report_options = self._get_options(options)
        searchview_dict = {'options': self.report_options, 'context': self.env.context}

        report_manager = self._get_report_manager(self.report_options)
        info = {'options': self.report_options,
                'context': self.env.context,
                'report_manager_id': report_manager.id,
                'footnotes': [{'id': f.id, 'line': f.line, 'text': f.text} for f in report_manager.footnotes_ids],
                'buttons': self._get_reports_buttons_in_sequence(),
                'main_html': self.get_html(self.report_options),
                'searchview_html': self.env['ir.ui.view'].render_template(
                    self._get_templates().get('search_template', 'account_report.search_template'),
                    values=searchview_dict),
                }
        return info

    def _check_report_security(self, options):
        '''The security check must be done in this method. It ensures no-one can by-passing some access rules
        (e.g. falsifying the options).

        :param options:     The report options.
        '''
        # Check the options has not been falsified in order to access not allowed companies.
        user_company_ids = self.env.user.company_ids.ids
        if options.get('multi_company'):
            group_multi_company = self.env.ref('base.group_multi_company')
            if self.env.user.id not in group_multi_company.users.ids:
                options.pop('multi_company')
            else:
                options['multi_company'] = [opt for opt in options['multi_company'] if opt['id'] in user_company_ids]

    def get_html(self, options, line_id=None, additional_context=None):
        '''
        return the html value of report, or html value of unfolded line
        * if line_id is set, the template used will be the line_template
        otherwise it uses the main_template. Reason is for efficiency, when unfolding a line in the report
        we don't want to reload all lines, just get the one we unfolded.
        '''
        # Check the security before updating the context to make sure the options are safe.
        self._check_report_security(options)

        # Prevent inconsistency between options and context.
        self = self.with_context(self._set_context(options))

        templates = self._get_templates()
        report_manager = self._get_report_manager(options)
        report = {'name': self._get_report_name(),
                  'summary': report_manager.summary,
                  'company_name': self.env.user.company_id.name, }
        lines = self._get_item_lines(options)

        rcontext = {'report': report,
                    'lines': {'columns_header': self.get_header(options), 'lines': lines},
                    'options': options,
                    'context': self.env.context,
                    'model': self,
                    }
        if additional_context and type(additional_context) == dict:
            rcontext.update(additional_context)

        render_template = templates.get('main_template', 'financial_statement_reporting.main_template')
        html = self.env['ir.ui.view'].render_template(
            render_template,
            values=dict(rcontext),
        )
        return html

    def _get_reports_buttons_in_sequence(self):
        return sorted(self._get_reports_buttons(), key=lambda x: x.get('sequence', 9))

    def _get_reports_buttons(self):
        return [
            # {'name': _('Export (XLSX)'), 'sequence': 1, 'action': 'print_xlsx', 'file_export_type': _('XLSX')},
        ]

    def _get_report_manager(self, options):
        domain = [('report_name', '=', self._name)]
        domain = (domain + [('financial_report_id', '=', self.id)]) if 'id' in dir(self) else domain
        selected_companies = []
        # if options.get('multi_company'):
        #     selected_companies = [c['id'] for c in options['multi_company'] if c.get('selected')]
        if len(selected_companies) == 1:
            domain += [('company_id', '=', selected_companies[0])]
        existing_manager = self.env['account.report.manager'].search(domain, limit=1)
        if not existing_manager:
            existing_manager = self.env['account.report.manager'].create(
                {'report_name': self._name, 'company_id': selected_companies and selected_companies[0] or False,
                 'financial_report_id': self.id if 'id' in dir(self) else False})
        return existing_manager

    @api.model
    def format_value(self, amount, currency=False, blank_if_zero=False):
        ''' Format amount to have a monetary display (with a currency symbol).
        E.g: 1000 => 1000.0 $

        :param amount:          A number.
        :param currency:        An optional res.currency record.
        :param blank_if_zero:   An optional flag forcing the string to be empty if amount is zero.
        :return:                The formatted amount as a string.
        '''
        currency_id = currency or self.env.user.company_id.currency_id
        if currency_id.is_zero(amount):
            if blank_if_zero:
                return ''
            # don't print -0.0 in reports
            amount = abs(amount)

        if self.env.context.get('no_format'):
            return amount
        return formatLang(self.env, amount, currency_obj=currency_id)

    def format_date(self, options, dt_filter='date'):
        date_from = fields.Date.from_string(options[dt_filter]['date_from'])
        date_to = fields.Date.from_string(options[dt_filter]['date_to'])
        return self._get_dates_period(options, date_from, date_to, options['date']['mode'])['string']

    def _replace_class(self):
        """When printing pdf, we sometime want to remove/add/replace class for the report to look a bit different on paper
        this method is used for this, it will replace occurence of value key by the dict value in the generated pdf
        """
        return {b'o_account_reports_no_print': b'', b'table-responsive': b'', b'<a': b'<span', b'</a>': b'</span>'}

    def get_txt(self, options):
        return False

    def _get_item_lines(self, options):
        lines = []
        current_date = datetime.strptime(options.get('date').get('date_from'), '%Y-%m-%d').date()
        self.fiscal_year = self.env.user.company_id.compute_fiscalyear_dates(current_date)
        self.items = {}
        self.headings = {}
        self.get_cashf_low_statement_by_period(options)

        headers = self.env['financial.statement.heading'].search(
            ['&', ('parent_id', '=', False), ('table_id.code', '=', 'TFT')])
        if headers:
            for header in headers:
                line = {
                    'id': header.id,
                    'name': header.ref,
                    'class': 'table_parent',
                    'columns': [
                        {'name': header.name, 'title': header.name, 'class': 'table_parent'},
                        {'name': self.format_value(0.0, blank_if_zero=1), 'class': 'number'},
                        {'name': self.format_value(0.0, blank_if_zero=1), 'class': 'number'}
                    ]
                }
                lines.append(line)
                if header.child_ids:
                    for child in header.child_ids:
                        child_line = {
                            'id': child.id,
                            'name': child.ref,
                            'columns': [
                                {'name': child.name, 'title': child.name},
                            ]
                        }
                        for key in range(2):
                            if child.ref in self.headings.keys() and key < len(self.headings[child.ref]) :
                                _logger.info("============= %s --- %s ---- %s", len(self.headings[child.ref]), self.headings[child.ref], key)
                                child_line.get('columns').extend(
                                    [{'name': self.format_value(self.headings[child.ref][key], blank_if_zero=True),
                                      'class': 'number'}])
                            else:
                                child_line.get('columns').extend(
                                    [{'name': self.format_value(0.0, blank_if_zero=True), 'class': 'number'}])
                        lines.append(child_line)
        return lines

    def get_cashf_low_statement_by_period(self, options):
        if options.get('date').get('filter') in 'this_year' or options.get('date').get('filter') == 'custom':
            self._get_years_dates()

    def _get_query_cash_flow(self):
        company_id = self.env.user.company_id.id
        query = """
            SELECT h.ref,
            SUM(CASE
                    WHEN fha.operation = 'sum_movement_credit' and fha.fiscal_period = 'n'
                        THEN fha.sign * account.aml_credit
                    WHEN fha.operation = 'sum_movement_credit' and fha.fiscal_period = 'n_1'
                        THEN fha.sign * account.initial_balance_credit
                
                    WHEN fha.operation = 'sum_movement_debit' and fha.fiscal_period = 'n'
                        THEN fha.sign * account.aml_debit
                    WHEN fha.operation = 'sum_movement_debit' and fha.fiscal_period = 'n_1'
                        THEN fha.sign * account.initial_balance_debit
                
                    WHEN fha.operation = 'sum_balance_credit' and fha.fiscal_period = 'n'
                        THEN fha.sign * (account.aml_credit - account.aml_debit)
                    WHEN fha.operation = 'sum_balance_credit' and fha.fiscal_period = 'n_1'
                        THEN fha.sign * (account.initial_balance_credit - account.initial_balance_debit)
                    WHEN fha.operation = 'sum_balance_credit' and fha.fiscal_period = 'n_n_1'
                        THEN fha.sign * (account.final_balance_credit - account.final_balance_debit)
                    WHEN fha.operation = 'sum_balance_credit' and fha.fiscal_period = 'n_1_n_2'
                        THEN fha.sign * (account.initial_balance_credit - account.initial_balance_debit)
                
                    WHEN fha.operation = 'sum_balance_debit' and fha.fiscal_period = 'n'
                        THEN fha.sign * (account.aml_debit - account.aml_credit)
                    WHEN fha.operation = 'sum_balance_debit' and fha.fiscal_period = 'n_1'
                        THEN fha.sign * (account.initial_balance_debit - account.initial_balance_credit)
                    WHEN fha.operation = 'sum_balance_debit' and fha.fiscal_period = 'n_n_1'
                        THEN fha.sign * (account.final_balance_debit - account.final_balance_credit)
                    WHEN fha.operation = 'sum_balance_debit' and fha.fiscal_period = 'n_1_n_2'
                        THEN fha.sign * (account.initial_balance_debit - account.initial_balance_credit)
                
                    WHEN fha.operation = 'sum_debit' AND fha.fiscal_period = 'n'
                        THEN fha.sign * account.final_balance_debit
                    WHEN fha.operation = 'sum_credit' AND fha.fiscal_period = 'n'
                        THEN fha.sign * account.final_balance_credit
                
                    WHEN fha.operation = 'sum_debit' AND fha.fiscal_period = 'n_1'
                        THEN fha.sign * account.initial_balance_debit
                    WHEN fha.operation = 'sum_credit' AND fha.fiscal_period = 'n_1'
                        THEN fha.sign * account.initial_balance_credit
            END) AS amount
            FROM financial_statement_heading AS h
            INNER JOIN financial_statement_heading AS p ON p.id = h.parent_id
            INNER JOIN financial_statement_table AS ft ON (ft.id = p.table_id AND ft.code = 'TFT')
            INNER JOIN financial_rel_heading_account AS fha ON fha.heading_id = h.id
            INNER JOIN (
                SELECT r.code,
                COALESCE(CASE 
                WHEN r.start_balance_debit - r.start_balance_credit > 0 
                THEN r.start_balance_debit - r.start_balance_credit
                END, 0) AS initial_balance_debit,  
                COALESCE(CASE 
                WHEN r.start_balance_debit - r.start_balance_credit < 0 
                THEN r.start_balance_credit - r.start_balance_debit
                END, 0) AS initial_balance_credit,  r.aml_debit, r.aml_credit, 
                COALESCE(CASE 
                WHEN r.start_balance_debit - r.start_balance_credit + r.aml_debit - r.aml_credit > 0 
                THEN r.start_balance_debit - r.start_balance_credit + r.aml_debit - r.aml_credit
                END, 0) AS final_balance_debit, 
                COALESCE(CASE 
                WHEN r.start_balance_debit - r.start_balance_credit + r.aml_debit - r.aml_credit < 0 
                THEN r.start_balance_credit - r.start_balance_debit + r.aml_credit - r.aml_debit
                END, 0) AS final_balance_credit
                FROM (SELECT account.code,
                    COALESCE(SUM(CASE WHEN aml.date < %s THEN aml.debit END),0) AS start_balance_debit,
                    COALESCE(SUM(CASE WHEN aml.date < %s THEN aml.credit END),0) AS start_balance_credit,
                    COALESCE(SUM(CASE WHEN aml.date BETWEEN %s AND %s THEN aml.debit END),0) AS aml_debit,
                    COALESCE(SUM(CASE WHEN aml.date BETWEEN %s AND %s THEN aml.credit END),0) AS aml_credit
                    FROM account_account AS account
                    INNER JOIN account_move_line AS aml ON aml.account_id = account.id
                    WHERE aml.date <= %s
                    AND aml.company_id = """ + str(company_id) + """
                    AND account.company_id = """ + str(company_id) + """
                    GROUP BY account.code
                    ORDER BY account.code
                ) AS r
                WHERE r.start_balance_debit - r.start_balance_credit - r.aml_debit - r.aml_credit <> 0
            ) AS account ON account.code LIKE CONCAT(fha.input_account, %s)
            WHERE fha.except_account IS NULL OR (fha.except_account IS NOT NULL AND account.code !~ fha.except_account)
            GROUP BY h.ref
        """
        return query

    def _get_years_dates(self):
        current_date, end_date = self.fiscal_year['date_from'], self.fiscal_year['date_from'] - relativedelta(years=3)

        while current_date > end_date:
            fiscal_year = self.env.user.company_id.compute_fiscalyear_dates(current_date)
            dates = [
                fiscal_year['date_from'], fiscal_year['date_from'],
                fiscal_year['date_from'], fiscal_year['date_to'],
                fiscal_year['date_from'], fiscal_year['date_to'],
                fiscal_year['date_to'], '%'
            ]

            query = self._get_query_cash_flow()
            self._cr.execute(query, dates)
            child_lines = self._cr.dictfetchall()

            for line in child_lines:
                if line['ref'] not in self.headings.keys():
                    self.headings[line['ref']] = []
                self.headings[line['ref']].append(line['amount'])

            current_date = current_date - relativedelta(years=1)

    def _get_query(self):
        company_id = self.env.user.company_id.id
        query = '''
                SELECT r.code, r.balance_debit, r.balance_credit, r.aml_debit, r.aml_credit, 
                ABS(COALESCE(CASE 
                WHEN r.balance_debit - r.balance_credit - r.aml_debit - r.aml_credit > 0 
                THEN r.balance_debit - r.balance_credit - r.aml_debit - r.aml_credit
                END, 0)) AS debit_balance, 
                ABS(COALESCE(CASE 
                WHEN r.balance_debit - r.balance_credit - r.aml_debit - r.aml_credit < 0 
                THEN r.balance_debit - r.balance_credit - r.aml_debit - r.aml_credit
                END, 0)) AS credit_balance
                FROM (SELECT account.code,
                    COALESCE(SUM(CASE WHEN aml.date < %s THEN aml.debit END),0) AS balance_debit,
                    COALESCE(SUM(CASE WHEN aml.date < %s THEN aml.credit END),0) AS balance_credit,
                    COALESCE(SUM(CASE WHEN aml.date BETWEEN %s AND %s THEN aml.debit END),0) AS aml_debit,
                    COALESCE(SUM(CASE WHEN aml.date BETWEEN %s AND %s THEN aml.credit END),0) AS aml_credit
                    FROM account_account AS account
                    INNER JOIN account_move_line AS aml ON aml.account_id = account.id
                    WHERE aml.date <= %s
                    AND aml.company_id = ''' + str(company_id) + '''
                    AND account.company_id = ''' + str(company_id) + '''
                    GROUP BY account.code
                    ORDER BY account.code
                ) AS r
                WHERE r.balance_debit - r.balance_credit - r.aml_debit - r.aml_credit <> 0
        '''

        return query
