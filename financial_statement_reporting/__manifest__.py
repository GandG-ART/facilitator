# -*- coding: utf-8 -*-
{
    'name': "Rapport des Etats financiers",

    'summary': """
        Financial Statement Report
    """,

    'description': """
        Financial Statement Report
    """,

    'author': "G&G Professional Services",
    'website': "http://www.gandgcorp.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/12.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Accounting',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'account_reports', 'l10n_pcgo'],

    # always loaded
    'data': [
        'views/heading.xml',
        'views/table.xml',
        'views/assets.xml',
        'views/financial_statement_reporting_view.xml',
        'views/search_template_view.xml',
        'data/financial_statement_actions.xml',
        'data/financial_statement_reporting.xml',
        'data/heading_table_data.xml',
        'data/income_statement_data.xml',
        'data/passive_balance_sheet_data.xml',
        'data/actif_balance_sheet_data.xml',
        'data/cash_flow_table_data.xml',
        # 'wizard/financial_statements_wizard.xml',
        # 'wizard/financial_rel_heading_account_wizard.xml',
        'security/ir.model.access.csv',
    ],
    'qweb': [
        'static/src/xml/financial_statement_reporting.xml'
    ],
}