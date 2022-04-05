# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging

from odoo import http
from odoo.addons.web.controllers.main import _serialize_exception
from odoo.http import content_disposition, request
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)


class FinancialStatementReportingController(http.Controller):

    @http.route('/financial_reports', type='http', auth='user', methods=['POST'], csrf=False)
    def get_report(self, model, options, output_format, token, **kw):
        uid = request.session.uid
        report_obj = request.env[model].sudo(uid)
        options = json.loads(options)
        report_name = report_obj.get_report_filename(options)
        try:
            if output_format == 'xlsx':
                response = request.make_response(
                    None,
                    headers=[
                        ('Content-Type', report_obj.get_export_mime_type('xlsx')),
                        ('Content-Disposition', content_disposition(report_name + '.xlsx'))
                    ]
                )
                response.stream.write(report_obj.get_xlsx(options))
            response.set_cookie('fileToken', token)
            return response
        except Exception as e:
            se = _serialize_exception(e)
            error = {
                'code': 200,
                'message': 'Odoo Server Error',
                'data': se
            }
            return request.make_response(html_escape(json.dumps(error)))

    @http.route('/financial_statement_reports', type='http', auth='user', methods=['POST'], csrf=False)
    def get_report_xlsx(self, model, options, output_format, token, report_name, **kw):
        uid = request.session.uid
        report_obj = request.env[model].sudo(uid)
        options = json.loads(options)
        try:
            if output_format == 'xlsx':
                response = request.make_response(
                    None,
                    headers=[('Content-Type', 'application/vnd.ms-excel'),
                             ('Content-Disposition', content_disposition(report_name + '.xlsx'))
                             ]
                )
                report_obj.get_xlsx_report(options, response)
            response.set_cookie('fileToken', token)
            return response
        except Exception as e:
            se = _serialize_exception(e)
            error = {
                'code': 200,
                'message': 'Odoo Server Error',
                'data': se
            }
            return request.make_response(html_escape(json.dumps(error)))
