import json
import logging

from odoo import models
from odoo.http import request
from dateutil.relativedelta import relativedelta
from odoo import models, api, fields
from datetime import datetime

_logger = logging.getLogger(__name__)


class Http(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        ICP = request.env['ir.config_parameter'].sudo()
        User = request.env['res.users']
        database_expiration_date = datetime.now() + relativedelta(days=40)

        if User.has_group('base.group_system'):
            warn_enterprise = 'admin'
        elif User.has_group('base.group_user'):
            warn_enterprise = 'user'
        else:
            warn_enterprise = False

        result = super(Http, self).session_info()
        result['warning'] = warn_enterprise
        result['expiration_date'] = database_expiration_date.strftime("%Y-%m-%d %H:%M:%S")
        result['expiration_reason'] = ICP.get_param('database.expiration_reason')

        _logger.info("=============== %s ", result)
        return result
