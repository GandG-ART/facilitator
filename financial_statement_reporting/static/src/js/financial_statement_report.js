odoo.define('financial_statement_reporting.financial_statement_report', function (require) {
'use strict';

var core = require('web.core');
var Context = require('web.Context');
var AbstractAction = require('web.AbstractAction');
var ControlPanelMixin = require('web.ControlPanelMixin');
var Dialog = require('web.Dialog');
var datepicker = require('web.datepicker');
var session = require('web.session');
var field_utils = require('web.field_utils');
var RelationalFields = require('web.relational_fields');
var StandaloneFieldManagerMixin = require('web.StandaloneFieldManagerMixin');
var WarningDialog = require('web.CrashManager').WarningDialog;
var Widget = require('web.Widget');

var QWeb = core.qweb;
var _t = core._t;

var FinancialStatementReportsWidget = AbstractAction.extend(ControlPanelMixin, {
    hasControlPanel: true,
    init: function(parent, action) {
        this.actionManager = parent;
        this.report_model = action.context.model;
        this.odoo_context = action.context;
        this.report_options = action.options || false;
        this.ignore_session = action.ignore_session;
        if ((action.ignore_session === 'read' || action.ignore_session === 'both') !== true) {
            var persist_key = 'report:'+this.report_model+':'+this.financial_id+':'+session.company_id;
            this.report_options = JSON.parse(sessionStorage.getItem(persist_key)) || this.report_options;
        }
        return this._super.apply(this, arguments);
    },
    start: function() {
        var self = this;
        var extra_info = this._rpc({
                model: self.report_model,
                method: 'get_report_informations',
                args: [self.financial_id, self.report_options],
                context: self.odoo_context,
            })
            .then(function(result){
                return self.parse_reports_informations(result);
            });
        return Promise.all([extra_info, this._super.apply(this, arguments)]).then(function() {
            self.render();
        });
    },
    parse_reports_informations: function(values) {
        this.report_options = values.options;
        this.odoo_context = values.context;
        this.report_manager_id = values.report_manager_id;
        this.buttons = values.buttons;

        this.main_html = values.main_html;
        this.$searchview_buttons = $(values.searchview_html);
        this.persist_options();
    },
    persist_options: function() {
        if ((this.ignore_session === 'write' || this.ignore_session === 'both') !== true) {
            var persist_key = 'report:'+this.report_model+':'+this.financial_id+':'+session.company_id;
            sessionStorage.setItem(persist_key, JSON.stringify(this.report_options));
        }
    },
    // We need this method to rerender the control panel when going back in the breadcrumb
    do_show: function() {
        this._super.apply(this, arguments);
        this.update_cp();
    },
    // Updates the control panel and render the elements that have yet to be rendered
    update_cp: function() {
        if (!this.$buttons) {
            this.renderButtons();
        }
        var status = {
            cp_content: {
                $buttons: this.$buttons,
                $searchview_buttons: this.$searchview_buttons,
                $pager: this.$pager,
                $searchview: this.$searchview,
            },
        };

        return this.update_control_panel(status, {clear: true});
    },
    reload: function() {
        var self = this;
        return this._rpc({
                model: this.report_model,
                method: 'get_report_informations',
                args: [self.financial_id, self.report_options],
                context: self.odoo_context,
            })
            .then(function(result){
                self.parse_reports_informations(result);
                return self.render();
            });
    },
    render: function() {
        var self = this;
        this.render_template();
        this.render_searchview_buttons();
        this.update_cp();
    },
    render_template: function() {
        this.$el.html(this.main_html);
    },
    render_searchview_buttons: function() {
        var self = this;
        var $datetimepickers = this.$searchview_buttons.find('.js_account_reports_datetimepicker');
        var options = {
            locale : moment.locale(),
            format : 'L',
            icons: {
                date: "fa fa-calendar",
            },
        };
        // attach datepicker
        $datetimepickers.each(function () {
            var name = $(this).find('input').attr('name');
            var defaultValue = $(this).data('default-value');
            $(this).datetimepicker(options);
            var dt = new datepicker.DateWidget(options);
            dt.replace($(this)).then(function () {
                dt.$el.find('input').attr('name', name);
                if (defaultValue) { // Set its default value if there is one
                    dt.setValue(moment(defaultValue));
                }
            });
        });
        // format date that needs to be show in user lang
        _.each(this.$searchview_buttons.find('.js_format_date'), function(dt) {
            var date_value = $(dt).html();
            $(dt).html((new moment(date_value)).format('ll'));
        });
         // fold all menu
        this.$searchview_buttons.find('.js_foldable_trigger').click(function (event) {
            $(this).toggleClass('o_closed_menu o_open_menu');
            self.$searchview_buttons.find('.o_foldable_menu[data-filter="'+$(this).data('filter')+'"]').toggleClass('o_closed_menu');
        });
        // render filter (add selected class to the options that are selected)
        _.each(self.report_options, function(k) {
            if (k!== null && k.filter !== undefined) {
                self.$searchview_buttons.find('[data-filter="'+k.filter+'"]').addClass('selected');
            }
        });
        // click events
        this.$searchview_buttons.find('.js_account_report_date_filter').click(function (event) {
            self.report_options.date.filter = $(this).data('filter');
            var error = false;
            if ($(this).data('filter') === 'custom') {
                var date_from = self.$searchview_buttons.find('.o_datepicker_input[name="date_from"]');
                var date_to = self.$searchview_buttons.find('.o_datepicker_input[name="date_to"]');
                if (date_from.length > 0){
                    error = date_from.val() === "" || date_to.val() === "";
                    self.report_options.date.date_from = field_utils.parse.date(date_from.val());
                    self.report_options.date.date_to = field_utils.parse.date(date_to.val());
                }
                else {
                    error = date_to.val() === "";
                    self.report_options.date.date_to = field_utils.parse.date(date_to.val());
                }
            }
            if (error) {
                new WarningDialog(self, {
                    title: _t("Odoo Warning"),
                }, {
                    message: _t("Date cannot be empty")
                }).open();
            } else {
                self.reload();
            }
        });
        this.$searchview_buttons.find('.js_account_report_date_cmp_filter').click(function (event) {
            self.report_options.comparison.filter = $(this).data('filter');
            var error = false;
            var number_period = $(this).parent().find('input[name="periods_number"]');
            self.report_options.comparison.number_period = (number_period.length > 0) ? parseInt(number_period.val()) : 1;
            if ($(this).data('filter') === 'custom') {
                var date_from = self.$searchview_buttons.find('.o_datepicker_input[name="date_from_cmp"]');
                var date_to = self.$searchview_buttons.find('.o_datepicker_input[name="date_to_cmp"]');
                if (date_from.length > 0) {
                    error = date_from.val() === "" || date_to.val() === "";
                    self.report_options.comparison.date_from = field_utils.parse.date(date_from.val());
                    self.report_options.comparison.date_to = field_utils.parse.date(date_to.val());
                }
                else {
                    error = date_to.val() === "";
                    self.report_options.comparison.date_to = field_utils.parse.date(date_to.val());
                }
            }
            if (error) {
                new WarningDialog(self, {
                    title: _t("Odoo Warning"),
                }, {
                    message: _t("Date cannot be empty")
                }).open();
            } else {
                self.reload();
            }
        });
    },
    format_date: function(moment_date) {
        var date_format = 'YYYY-MM-DD';
        return moment_date.format(date_format);
    },
    renderButtons: function() {
        var self = this;
        this.$buttons = $(QWeb.render("FinancialStatement.buttons", {buttons: this.buttons}));
        // bind actions
        _.each(self.$buttons.siblings('button'), function(el) {
            $(el).click(function() {
                self.$buttons.attr('disabled', true);
                return self._rpc({
                        model: self.report_model,
                        method: $(el).attr('action'),
                        args: [1, self.report_options],
                        context: self.odoo_context,
                    })
                    .then(function(result){
                        var doActionProm = self.do_action(result);
                        self.$buttons.attr('disabled', false);
                        return doActionProm;
                    })
                    .always(function() {
                        self.$buttons.attr('disabled', false);
                    });
            });
        });
        return this.$buttons;
    },
    trigger_action: function(e) {
        e.stopPropagation();
        var self = this;
        var action = $(e.target).attr('action');
        var id = $(e.target).parents('td').data('id');
        var params = $(e.target).data();
        var context = new Context(this.odoo_context, params.actionContext || {}, {active_id: id});

        params = _.omit(params, 'actionContext');
        if (action) {
            return this._rpc({
                    model: this.report_model,
                    method: action,
                    args: [this.financial_id, this.report_options, params],
                    context: context.eval(),
                })
                .then(function(result){
                    return self.do_action(result);
                });
        }
    },
});

core.action_registry.add('financial_statement_reporting_report', FinancialStatementReportsWidget);

return FinancialStatementReportsWidget;

});
