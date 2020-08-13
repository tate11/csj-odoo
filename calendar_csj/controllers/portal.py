# -*- coding: utf-8 -*-

from collections import OrderedDict
from operator import itemgetter
from odoo import http, fields, _
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.tools import groupby as groupbyelem
from odoo import models, fields, api
from datetime import datetime,timedelta
from dateutil.relativedelta import relativedelta
from odoo.tools import html2plaintext, DEFAULT_SERVER_DATETIME_FORMAT as dtf
import pytz
from odoo.tools.misc import get_lang
from babel.dates import format_datetime, format_date
from werkzeug.urls import url_encode
from datetime import datetime

from odoo.osv.expression import OR

import logging
_logger = logging.getLogger(__name__)


class CustomerPortal(CustomerPortal):

    def _prepare_portal_layout_values(self):
        values = super(CustomerPortal, self)._prepare_portal_layout_values()
        # when partner is not scheduler they can only view their own
        partner = request.env.user.partner_id
        judged_id = partner.parent_id
        domain = []
        if partner.appointment_type != 'scheduler':
            domain += [('partner_id', '=', judged_id.id)]
        values['appointment_count'] = request.env['calendar.appointment'].search_count(domain)
        return values

    # ------------------------------------------------------------
    # My Appointments
    # ------------------------------------------------------------
    def _appointment_get_page_view_values(self, appointment, access_token, **kwargs):
        values = {
            'page_name': 'appointment',
            'appointment': appointment,
        }
        return self._get_page_view_values(appointment, access_token, values, 'my_appointment_history', False, **kwargs)


    @http.route(['/my/appointments', '/my/appointments/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_appointments(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, search=None, search_in='content', groupby='appointment', **kw):
        values = self._prepare_portal_layout_values()

        searchbar_sortings = {
            'date': {'label': _('Fecha de Realización'), 'order': 'calendar_datetime desc'},
            'appointment_code': {'label': _('Appointment ID'), 'order': 'appointment_code desc'},
            'state': {'label': _('Estado'), 'order': 'state'},
            'city_id': {'label': _('Ciudad'), 'order': 'name'},
            'country_state_id': {'label': _('Departamento'), 'order': 'name'},
            'process_number': {'label': _('Número de Proceso'), 'order': 'process_number'},
        }
        searchbar_filters = {
            'all': {'label': _('Todos'), 'domain': []},
            'today': {'label': _('Hoy'), 'domain': [('calendar_datetime','<',datetime(2020,8,12,23,59,59)),('calendar_datetime','>',datetime(2020,8,12,0,0,1))]},
            'month': {'label': _('Último Mes'), 'domain': [('calendar_datetime','>',datetime(2020,8,1,0,0,1)),('calendar_datetime','<',datetime(2020,8,31,23,59,59))]},
            'cancel': {'label': _('Cancelados'), 'domain': [('state','=','cancel')]},
            'realized': {'label': _('Realizados'), 'domain': [('state','=','realized')]},
            'open': {'label': _('Realizados'), 'domain': [('state','=','open')]},
        }

        searchbar_inputs = {
            'appointment_code': {'input': 'appointment_code', 'label': _('Buscar <span class="nolabel"> (en Id Agendamiento)</span>')},
            'process_number': {'input': 'process_number', 'label': _('Buscar por Número de Proceso')},
            'applicant_id': {'input': 'applicant_id', 'label': _('Buscar por Nombre Solicitante')},
            'declarant_text': {'input': 'declarant_text', 'label': _('Buscar por Declarante')},
            'tag_number': {'input': 'tag_number', 'label': _('Buscar Etiqueta')},
            'indicted_text': {'input': 'indicted_text', 'label': _('Buscar por Procesado')},
            'applicant_email': {'input': 'applicant_email', 'label': _('Buscar por Email del Aplicante')},
            'lifesize_meeting_ext': {'input': 'lifesize_meeting_ext', 'label': _('Buscar por Ext reunión Lifesize')},
            'name': {'input': 'name', 'label': _('Buscar por API Lifesize')},
            'state': {'input': 'state', 'label': _('Buscar por Estado')},
            'all': {'input': 'all', 'label': _('Buscar en Todos')},
        }
        searchbar_groupby = {
            'none': {'input': 'none', 'label': _('None')},
            'appointment': {'input': 'appointment_code', 'label': _('Appointment')},
            'state': {'input': 'state', 'label': _('Estado')},
        }


        # extends filterby criteria with project the customer has access to
        """
        appointments = request.env['calendar.appointment'].search([])
        for appointment in appointments:
            searchbar_filters.update({
                str(appointment.id): {'label': appointment.name, 'domain': [('state', '=', 'open')]}
            })
        """

        appointments = request.env['calendar.appointment'].search([
            #('partner_id', '=', partner.id),
        ])
        #for appointment in appointments:
        #    searchbar_filters.update({
        #        str(appointment.id): {'label': appointment.name, 'domain': [('appointment_id', '=', appointment.id)]}
        #    })

        # extends filterby criteria with project (criteria name is the project id)
        # Note: portal users can't view projects they don't follow
        #appointment_groups = request.env['calendar.appointment'].read_group([('project_id', 'not in', projects.ids)],
        #                                                        ['project_id'], ['project_id'])
        """
        for group in appointment_groups:
            proj_id = group['project_id'][0] if group['project_id'] else False
            proj_name = group['project_id'][1] if group['project_id'] else _('Others')
            searchbar_filters.update({
                str(proj_id): {'label': proj_name, 'domain': [('project_id', '=', proj_id)]}
            })
        """
        # default sort by value
        if not sortby:
            sortby = 'appointment_code'
        order = searchbar_sortings[sortby]['order']
        # default filter by value
        if not filterby:
            filterby = 'all'
        domain = searchbar_filters[filterby]['domain']


        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        # archive groups - Default Group By 'create_date'
        archive_groups = self._get_archive_groups('calendar.appointment', domain)
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        # appointments count
        #appointment_count = Appointment.search_count(domain)

        # search
        if search and search_in:
            search_domain = []
            if search_in in ('appointment_code', 'all'):
                search_domain = OR([search_domain, [('appointment_code', 'ilike', search)]])
            if search_in in ('process_number', 'all'):
                search_domain = OR([search_domain, [('process_number', 'ilike', search)]])
            if search_in in ('applicant_id', 'all'):
                search_domain = OR([search_domain, [('applicant_id', 'ilike', search)]])
            if search_in in ('declarant_text', 'all'):
                search_domain = OR([search_domain, [('declarant_text', 'ilike', search)]])
            if search_in in ('tag_number', 'all'):
                search_domain = OR([search_domain, [('tag_number', 'ilike', search)]])
            if search_in in ('indicted_text', 'all'):
                search_domain = OR([search_domain, [('indicted_text', 'ilike', search)]])
            if search_in in ('applicant_email', 'all'):
                search_domain = OR([search_domain, [('applicant_email', 'ilike', search)]])
            domain += search_domain
            if search_in in ('lifesize_meeting_ext', 'all'):
                search_domain = OR([search_domain, [('lifesize_meeting_ext', 'ilike', search)]])
            domain += search_domain
            if search_in in ('name', 'all'):
                search_domain = OR([search_domain, [('name', 'ilike', search)]])
            domain += search_domain
            if search_in in ('state', 'all'):
                search_domain = OR([search_domain, [('state', 'ilike', search)]])
            domain += search_domain

        # task count
        appointment_count = request.env['calendar.appointment'].search_count(domain)


        # pager
        pager = portal_pager(
            url="/my/appointments",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
            total=appointment_count,
            page=page,
            step=self._items_per_page
        )

        """
        if groupby == 'state':
            order = "state, %s" % ''
        timesheets = Timesheet_sudo.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        if groupby == 'project':
            grouped_timesheets = [Timesheet_sudo.concat(*g) for k, g in groupbyelem(timesheets, itemgetter('project_id'))]
        else:
            grouped_timesheets = [timesheets]
        """

        # when partner is not scheduler they can only view their own
        partner = request.env.user.partner_id
        judged_id = partner.parent_id
        if partner.appointment_type != 'scheduler':
            domain += [('partner_id', '=', judged_id.id)]


        # content according to pager and archive selected
        appointments = request.env['calendar.appointment'].search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_appointments_history'] = appointments.ids[:100]

        values.update({
            'date': date_begin,
            'date_end': date_end,
            'appointments': appointments,
            'page_name': 'appointment',
            'archive_groups': archive_groups,
            'default_url': '/my/appointments',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_groupby': searchbar_groupby,
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'sortby': sortby,
            'groupby': groupby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby,
        })
        return request.render("calendar_csj.portal_my_appointments", values)


    @http.route([
        '/my/appointment/<int:appointment_id>'
    ], type='http', auth="user", website=True)
    def portal_my_appointment(self, appointment_id=None, access_token=None, **kw):
        try:
            appointment_sudo = self._document_check_access('calendar.appointment', appointment_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = self._appointment_get_page_view_values(appointment_sudo, access_token, **kw)
        return request.render("calendar_csj.portal_my_appointment", values)


    @http.route(['/my/appointment/<model("calendar.appointment"):appointment_id>/update/state/cancel'], type='http', auth="user", website=True)
    def portal_my_appointment_cancel(self, appointment_id=None, access_token=None, **kw):
        appointment_id.action_cancel()
        return request.redirect('/my/appointment/' + str(appointment_id.id))

    @http.route(['/my/appointment/<model("calendar.appointment"):appointment_id>/update/state/realized'], type='http', auth="user", website=True)
    def portal_my_appointment_realized(self, appointment_id=None, access_token=None, **kw):
        appointment_id.write({
            'state' : 'realized',
            'appointment_close_date': datetime.now(),
            'appointment_close_user_id': request.env.user.id,
        });
        return request.redirect('/my/appointment/' + str(appointment_id.id))

    @http.route(['/my/appointment/<model("calendar.appointment"):appointment_id>/update/state/unrealized'], type='http', auth="user", website=True)
    def portal_my_appointment_unrealized(self, appointment_id=None, access_token=None, **kw):
        appointment_id.write({
            'state' : 'unrealized',
            'appointment_close_date': datetime.now(),
            'appointment_close_user_id': request.env.user.id,
        });
        return request.redirect('/my/appointment/' + str(appointment_id.id))

    @http.route(['/my/appointment/<model("calendar.appointment"):appointment_id>/update/state/postpone'], type='http', auth="user", website=True)
    def portal_my_appointment_postpone(self, appointment_id=None, access_token=None, **kw):
        appointment_id.write({
            'state' : 'postpone',
            'appointment_close_date': datetime.now(),
            'appointment_close_user_id': request.env.user.id,
        });
        return request.redirect('/my/appointment/' + str(appointment_id.id))

    @http.route(['/my/appointment/<model("calendar.appointment"):appointment_id>/update/state/assist_postpone'], type='http', auth="user", website=True)
    def portal_my_appointment_assist_postpone(self, appointment_id=None, access_token=None, **kw):
        appointment_id.write({
            'state' : 'assist_postpone',
            'appointment_close_date': datetime.now(),
            'appointment_close_user_id': request.env.user.id,
        });
        return request.redirect('/my/appointment/' + str(appointment_id.id))

    @http.route(['/my/appointment/<model("calendar.appointment"):appointment_id>/update/state/assist_cancel'], type='http', auth="user", website=True)
    def portal_my_appointment_assist_cancel(self, appointment_id=None, access_token=None, **kw):
        appointment_id.write({
            'state' : 'assist_cancel',
            'appointment_close_date': datetime.now(),
            'appointment_close_user_id': request.env.user.id,
        });
        return request.redirect('/my/appointment/' + str(appointment_id.id))


    @http.route([
        '/my/appointment/<int:appointment_id>/update/all'
    ], type='http', auth="user", website=True)
    def portal_my_appointment_edit(self, appointment_id=None, access_token=None, **kw):
        try:
            appointment_sudo = self._document_check_access('calendar.appointment', appointment_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = self._appointment_get_page_view_values(appointment_sudo, access_token, **kw)
        return request.render("calendar_csj.portal_my_appointment_editall", values)



    @http.route(['/my/appointment/<model("calendar.appointment"):appointment_id>/update/all/submit'], type='http', auth="public", website=True, method=["POST"])
    def appointment_portal_edit_form_submit(self, calendar_datetime, calendar_duration, appointment_type, **kwargs):
        request.session['timezone'] = 'America/Bogota'
        _logger.error("*************************\n*******************************\n****************************+")
        _logger.error(calendar_datetime)
        day_name = format_datetime(datetime.strptime(calendar_datetime, "%Y-%m-%d %H:%M"), 'EEE', locale=get_lang(request.env).code)
        date_formated = format_datetime(datetime.strptime(calendar_datetime, "%Y-%m-%d %H:%M"), locale=get_lang(request.env).code)
        timezone = request.session['timezone']
        tz_session = pytz.timezone(timezone)
        date_start = tz_session.localize(fields.Datetime.from_string(calendar_datetime)).astimezone(pytz.utc)
        date_end = date_start + relativedelta(hours=float(calendar_duration))

        appointment_type_obj = request.env['calendar.appointment.type'].browse(appointment_type)
        _logger.error(appointment_type_obj)
        _logger.error(calendar_datetime)
        _logger.error(kwargs['appointment_id'])



        kwargs['appointment_id'].sudo().write({
            'calendar_datetime': date_start.strftime(dtf),
        })





        return request.redirect('/my/appointment/' + str(kwargs['appointment_id'].id))

        """
        return request.render("calendar_csj.portal_my_appointment", {
            #'partner_data': partner_data,
            'appointment_id': kwargs['appointment_id'].id,
        })
        """


        # check availability calendar.event with partner of appointment_type
        """
        if appointment_type_obj and appointment_type_obj.judged_id:
            _logger.error(appointment_type_obj.judged_id)
            if not appointment_type_obj.judged_id.calendar_verify_availability(date_start,date_end):
                return request.render("calendar_csj.portal_my_appointment_editall", {
                    'appointment_type': appointment_type,
                    'message': 'already_scheduling',
                    'appointment_id': appointment_id,
                })
        """
