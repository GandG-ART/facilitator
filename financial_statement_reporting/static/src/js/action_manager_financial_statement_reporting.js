odoo.define('financial_statement_reporting.ActionManager', function (require) {
"use strict";

/**
 * The purpose of this file is to add the support of Odoo actions of type
 * 'ir_actions_accounting_report_download' to the ActionManager.
 */

var ActionManager = require('web.ActionManager');
var crash_manager = require('web.crash_manager');
var framework = require('web.framework');
var session = require('web.session');

ActionManager.include({
    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Executes actions of type 'ir_actions_accounting_report_download'.
     *
     * @private
     * @param {Object} action the description of the action to execute
     * @returns {Promise} resolved when the report has been downloaded ;
     *   rejected if an error occurred during the report generation
     */
    _executeAccountingReportDownloadAction: function (action) {
        var self = this;
        framework.blockUI();
        var def = $.Deferred();
        return new Promise(function (resolve, reject) {
            session.get_file({
                url: '/financial_reports',
                data: action.data,
                success: def.resolve.bind(def),
                error: function () {
                    crash_manager.rpc_error.apply(crash_manager, arguments);
                    def.reject();
                },
                complete: framework.unblockUI,
            });
        });
    },
    /**
     * Executes actions of type 'ir_actions_financial_statement_report_download'.
     *
     * @private
     * @param {Object} action the description of the action to execute
     * @returns {Promise} resolved when the report has been downloaded ;
     *   rejected if an error occurred during the report generation
     */
    /*_executeFinancialStatementReportDownloadAction: function (action) {
        var self = this;
        framework.blockUI();
        var def = $.Deferred();
        return new Promise(function (resolve, reject) {
            session.get_file({
                url: '/financial_statement_reports',
                data: action.data,
                success: def.resolve.bind(def),
                error: function () {
                    crash_manager.rpc_error.apply(crash_manager, arguments);
                    def.reject();
                },
                complete: framework.unblockUI,
            });
        });
    },*/
    /**
     * Overrides to handle new actions.
     *
     * @override
     * @private
     */
    _handleAction: function (action, options) {
        if (action.type === 'ir_actions_accounting_report_download') {
            console.log("=================");
            return this._executeAccountingReportDownloadAction(action, options);
        }
        /*if (action.type === 'ir_actions_financial_statement_report_download') {
            return this._executeFinancialStatementReportDownloadAction(action, options);
        }*/
        return this._super.apply(this, arguments);
    },
});

});
