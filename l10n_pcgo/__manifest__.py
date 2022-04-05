# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Copyright (c) Optesis 2018 www.optesis.com

{
    'name': 'Syscohada révisé',
    'version': '12.2',
    'author': 'G&G professionnal services',
    'category': 'Localization',
    'description': """
                    Ce module permet de gérer le nouveau plan compable SYSCOHADA Révisé.
                    Ce module permet de gérer le nouveau plan compable SYSCOHADA Révisé
                    applicable à partir du 1er janvier 2018 pour tous les pays faisant partie de l'espace OHADA.
                    **Credits:** cabinet d'expertise comptable www.kyriex.com.
                    """,
    'website': 'http://www.gandgcorp.com',
    'depends': ['account','account_accountant'],
    'data': [
        'data/l10n_pcgo_chart_data.xml',
        'data/account_chart_template_data.xml',
        'data/account_tax_data.xml',
    ],

}
