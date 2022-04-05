import json
import logging
import io

from datetime import datetime
from openpyxl import load_workbook
from babel.dates import get_quarter_names
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.tools import date_utils
from odoo.tools.misc import formatLang, format_date, DEFAULT_SERVER_DATE_FORMAT
from odoo.tools.misc import xlsxwriter

_logger = logging.getLogger(__name__)


class PassiveBalanceSheet(models.AbstractModel):
    _name = 'financial.statement.passive.balance.sheet'
    _description = 'Bilan passif'

    filter_date = {'mode': 'range', 'filter': 'this_year'}
    period_size = {'this_year': 2, 'this_quarter': 4, 'custom': 2}
    items = {}

    @api.model
    def _get_options(self, previous_options=None):
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
            'show_quarter': False
        }

    def get_header(self, options):
        columns = self._get_columns_name(options)
        return [columns]

    def _get_columns_name(self, options):
        columns = [
            {'name': 'Ref', 'class': 'number'},
            {'name': _('Passif')},
        ]
        date_option = options.get('date')
        return columns + self.get_heading_items_header(date_option)

    def get_heading_items_header(self, date_options):
        fiscal_year = self.env.user.company_id.compute_fiscalyear_dates(
            datetime.strptime(date_options.get('date_from'), '%Y-%m-%d').date())
        date_from, date_to = fiscal_year['date_from'], fiscal_year['date_to']
        date_previous = date_to - relativedelta(years=1)
        columns = []
        if 'this_quarter' == date_options.get('filter'):
            while date_from < date_to:
                quarter_names = get_quarter_names('abbreviated', locale=self.env.context.get('lang') or 'fr_FR')
                string = u'%s\N{NO-BREAK SPACE}%s' % (
                    quarter_names[date_utils.get_quarter_number(date_from)], date_from.year)
                date_from = date_from + relativedelta(months=3)
                columns.append({'name': _('%s' % string), 'class': 'number table_parent'})
        elif 'this_year' == date_options.get('filter') or date_options.get('filter') == 'custom':
            columns = [{'name': _('Exercice N (%s)' % date_to.year), 'class': 'number table_parent'},
                       {'name': _('Exercice N-1 (%s)' % date_previous.year), 'class': 'number table_parent'}]
        return columns

    def _get_period_name(self, date_from):
        string = None
        if self.filter_period == 'annual':
            string = date_from.strftime('%Y')
        elif self.filter_period == 'quarterly':
            quarter_names = get_quarter_names('abbreviated', locale=self.env.context.get('lang') or 'fr_FR')
            string = u'%s\N{NO-BREAK SPACE}%s' % (
                quarter_names[date_utils.get_quarter_number(date_from)], date_from.year)

        return string

    def _get_templates(self):
        return {
            'main_template': 'financial_statement_reporting.main_template',
            'main_table_header_template': 'financial_statement_reporting.main_table_header',
            'line_template': 'financial_statement_reporting.line_template',
            'search_template': 'financial_statement_reporting.search_template',
        }

    # TO BE OVERWRITTEN
    def _get_report_name(self):
        return _('Bilan passif')

    def get_report_filename(self, options):
        return self._get_report_name().lower().replace(' ', '_')

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
        options = self._get_options(options)

        searchview_dict = {'options': options, 'context': self.env.context}

        info = {'options': options,
                'context': self.env.context,
                'buttons': self._get_reports_buttons_in_sequence(),
                'main_html': self.get_html(options),
                'searchview_html': self.env['ir.ui.view'].render_template(
                    self._get_templates().get('search_template', 'account_report.search_template'),
                    values=searchview_dict),
                }
        return info

    def get_html(self, options, line_id=None, additional_context=None):
        '''
        return the html value of report, or html value of unfolded line
        * if line_id is set, the template used will be the line_template
        otherwise it uses the main_template. Reason is for efficiency, when unfolding a line in the report
        we don't want to reload all lines, just get the one we unfolded.
        '''

        # Prevent inconsistency between options and context.
        self = self.with_context(self._set_context(options))

        templates = self._get_templates()
        report = {'name': self._get_report_name(),
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
            {'action': 'print_xlsx', 'display_button': True},
            {'name': _('Export (XLSX)'), 'sequence': 1, 'action': 'print_xlsx', 'file_export_type': _('XLSX'), 'display_button': True},
        ]

    def _get_report_manager(self, options):
        domain = [('report_name', '=', self._name)]
        domain = (domain + [('financial_report_id', '=', self.id)]) if 'id' in dir(self) else domain
        selected_companies = []
        if options.get('multi_company'):
            selected_companies = [c['id'] for c in options['multi_company'] if c.get('selected')]
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

    def _get_item_lines(self, options):
        lines = []
        period_size = self.period_size.get(options.get('date').get('filter'))
        items = self.get_passive_balance_lines_by_period(options)
        headings = self.env['financial.statement.heading'].search(
            ['&', ('parent_id', '=', False), ('table_id.code', '=', 'BP')])
        for h in headings:
            if h.child_ids:
                for ch in h.child_ids:
                    line = {
                        'id': ch.id,
                        'name': ch.ref,
                        'columns': [
                            {'name': ch.name, 'title': ch.name},
                        ]
                    }
                    if ch.ref in items.keys():
                        for amount in items[ch.ref]:
                            line.get('columns').extend([{'name': self.format_value(amount, blank_if_zero=True), 'class': 'number'}])
                    lines.append(line)
            line = {
                'id': h.id,
                'name': h.ref,
                'class': 'table_parent',
                'columns': [
                    {'name': h.name, 'title': h.name, 'class': 'table_parent'}
                ]
            }
            for key in range(period_size):
                amount = 0
                operator = None
                for code in h.other.split(' '):
                    if code in items.keys():
                        if operator in ('+', '-') and key < len(items[code]):
                            if operator in '+':
                                amount += items[code][key]
                            elif operator in '-':
                                amount -= items[code][key]
                        elif not operator:
                            amount = items[code][key]
                    operator = code

                line.get('columns').extend(
                    [{'name': self.format_value(amount, blank_if_zero=True), 'class': 'number'}])
                if h.ref not in items.keys():
                    items[h.ref] = []
                items[h.ref].append(amount)
            lines.append(line)

        return lines

    def get_passive_balance_lines_by_period(self, options):
        filter_date = {
            'date_from': datetime.strptime(options.get('date').get('date_from'), '%Y-%m-%d').date(),
            'date_to': datetime.strptime(options.get('date').get('date_to'), '%Y-%m-%d').date()
        }
        if options.get('date').get('filter') in ('this_year', 'custom'):
            return self._get_years_dates(filter_date)

    def _get_query_passive_statement(self):
        company_id = self.env.user.company_id.id
        query = '''
                SELECT r.ref,
                    COALESCE(SUM(CASE
                        WHEN (r.operation = 'sum_credit' AND r.debit - r.credit < 0) 
                            THEN r.credit - r.debit
                        WHEN (r.operation = 'fiscal_year')
                            THEN r.debit - r.credit
                        WHEN (r.operation = 'sum_balance_credit')  
                            THEN r.credit - r.debit
                        WHEN (r.operation = 'sum_balance_debit') 
                            THEN r.debit - r.credit
                    END),0.0) AS amount
                FROM	
                    (
                        (SELECT h.ref, account.code, fha.operation,
                                SUM(mvl.debit) AS debit, SUM(mvl.credit) AS credit
                        FROM financial_statement_heading AS h
                        INNER JOIN financial_statement_heading AS p ON p.id = h.parent_id
                        INNER JOIN financial_statement_table AS ft ON (ft.id = p.table_id AND ft.code = 'BP')
                        INNER JOIN financial_rel_heading_account AS fha ON fha.heading_id = h.id
                        INNER JOIN account_account AS account ON account.code LIKE CONCAT(fha.input_account, %s)
                        LEFT JOIN account_move_line AS mvl ON mvl.account_id = account.id
                        WHERE (mvl.date <= %s OR mvl.date IS NULL)
                        AND (mvl.company_id = '''+ str(company_id) +''' OR mvl.company_id IS NULL)
                        AND account.company_id = '''+ str(company_id) +''' AND (fha.except_account IS NULL OR (fha.except_account IS NOT NULL AND account.code !~ fha.except_account))
                        AND fha.operation <> 'fiscal_year'
                        GROUP BY h.ref, account.code, fha.operation 
                        ORDER BY h.ref, account.code)
                        UNION ALL
                        (SELECT h.ref, account.code, fha.operation,
                                SUM(mvl.credit) AS credit, SUM(mvl.debit) AS debit
                        FROM financial_statement_heading AS h
                        INNER JOIN financial_statement_heading AS p ON p.id = h.parent_id
                        INNER JOIN financial_statement_table AS ft ON (ft.id = p.table_id AND ft.code = 'BP')
                        INNER JOIN financial_rel_heading_account AS fha ON fha.heading_id = h.id
                        INNER JOIN account_account AS account ON account.code LIKE CONCAT(fha.input_account, %s)
                        LEFT JOIN account_move_line AS mvl ON mvl.account_id = account.id
                        WHERE (mvl.date BETWEEN %s AND %s OR mvl.date IS NULL)
                        AND (mvl.company_id = '''+ str(company_id) +''' OR mvl.company_id IS NULL)
                        AND account.company_id = '''+ str(company_id) +''' AND (fha.except_account IS NULL OR (fha.except_account IS NOT NULL AND account.code !~ fha.except_account))
                        AND fha.operation = 'fiscal_year'
                        GROUP BY h.ref, account.code, fha.operation 
                        ORDER BY h.ref, account.code
                        )
                    ) AS r
                GROUP BY r.ref
                ORDER BY r.ref
        '''
        return query

    def _get_years_dates(self, filter_date):
        items = {}
        current_date, end_date = filter_date.get('date_to'), filter_date.get('date_to') - relativedelta(years=2)

        while current_date > end_date:
            fiscal_year = self.env.user.company_id.compute_fiscalyear_dates(current_date)

            query = self._get_query_passive_statement()
            self._cr.execute(query, ['%', fiscal_year['date_to'], '%', fiscal_year['date_from'], fiscal_year['date_to']])
            child_lines = self._cr.dictfetchall()
            for line in child_lines:
                if line['ref'] not in items.keys():
                    items[line['ref']] = []
                items[line['ref']].append(line['amount'])

            current_date = current_date - relativedelta(years=1)
        return items

    def _get_table(self, options):
        return self.get_header(options), self._get_item_lines(options)

    @api.model
    def get_export_mime_type(self, file_type):
        """ Returns the MIME type associated with a report export file type,
        for attachment generation.
        """
        type_mapping = {
            'xlsx': 'application/vnd.ms-excel',
            'pdf': 'application/pdf',
        }
        return type_mapping.get(file_type, False)

    def print_xlsx(self, options, response=None):
        return {
            'type': 'ir_actions_accounting_report_download',
            'data': {'model': self.env.context.get('model'),
                     'options': json.dumps(options),
                     'output_format': 'xlsx',
                     'financial_id': self.env.context.get('id'),
            }
        }

    def get_xlsx(self, options, response=None):
        objet_lists = [
            {'model': 'financial.statement.active.balance.sheet', 'name': 'BILAN PAYSAGE', 'start': 0, 'end_column': 5},
            {'model': 'financial.statement.passive.balance.sheet', 'name': 'BILAN PAYSAGE', 'start': 6,
             'blank_line': 23, 'end_column': 9},
        ]

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {
            'in_memory': True,
            'strings_to_formulas': False,
        })
        sheet = workbook.add_worksheet(self._get_report_name()[:31])

        title_style = workbook.add_format(
            {'font_name': 'Cambria', 'bold': False, 'border': 1, 'bg_color': '#5E813F', 'font_color': '#FFFFFF',
             'center_across': True})

        row_parent_style = workbook.add_format(
            {'font_name': 'Cambria', 'bold': False, 'border': 1, 'bg_color': '#5E813F', 'font_color': '#080808'})
        row_child_style = workbook.add_format(
            {'font_name': 'Cambria', 'bold': False, 'border': 1, 'bg_color': '#FFFFFF', 'font_color': '#080808'})

        # Set the first column width to 5
        sheet.set_column(0, 0, 5)
        sheet.set_column(6, 6, 5)
        sheet.set_column(1, 1, 60)
        sheet.set_column(7, 7, 60)
        sheet.set_column(2, 5, 25)
        sheet.set_column(8, 9, 25)

        for tb in objet_lists:
            y_offset = 0
            headers, lines = self.env[tb.get('model')].with_context(no_format=True)._get_table(options)

            # Add headers.
            for header in headers:
                x_offset = tb.get('start')
                for column in header:
                    column_name_formated = column.get('name', '').replace('<br/>', ' ').replace('&nbsp;', ' ')
                    colspan = column.get('colspan', 1)
                    if colspan == 1:
                        sheet.write(y_offset, x_offset, column_name_formated, title_style)
                    else:
                        sheet.merge_range(y_offset, x_offset, y_offset, x_offset + colspan - 1, column_name_formated,
                                          title_style)
                    x_offset += colspan
                y_offset += 1

            for y in range(0, len(lines)):
                index_line = y
                # write the first column, with a specific style to manage the indentation
                if 'class' in lines[y].keys() and lines[y]['class'] in 'table_parent':
                    style = row_parent_style
                else:
                    style = row_child_style

                if tb.get('blank_line') and y == tb.get('blank_line'):
                    sheet.write(index_line + y_offset, tb.get('start'), '', row_child_style)
                    index_line += 1
                elif tb.get('blank_line') and y > tb.get('blank_line'):
                    index_line += 1

                cell_type, cell_value = self._get_cell_type_value(lines[y])
                sheet.write(index_line + y_offset, tb.get('start'), cell_value, style)

                # write all the remaining cells
                index_column = 0
                for x in range(tb.get('start'), tb.get('end_column')):
                    cell_type, cell_value = self._get_cell_type_value(lines[y]['columns'][index_column])
                    if not cell_value:
                        cell_value = 0
                    sheet.write(index_line + y_offset, x + 1, cell_value, style)
                    index_column += 1

        workbook.close()
        output.seek(0)
        generated_file = output.read()
        output.close()

        return generated_file

    def _get_cell_type_value(self, cell):
        if 'date' not in cell.get('class', '') or not cell.get('name'):
            # cell is not a date
            return ('text', cell.get('name', ''))
        if isinstance(cell['name'], (float, datetime.date, datetime.datetime)):
            # the date is xlsx compatible
            return ('date', cell['name'])
        try:
            # the date is parsable to a xlsx compatible date
            lg = self.env['res.lang']._lang_get(self.env.user.lang) or get_lang(self.env)
            return ('date', datetime.datetime.strptime(cell['name'], lg.date_format))
        except:
            # the date is not parsable thus is returned as text
            return ('text', cell['name'])