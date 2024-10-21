from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class HelpdeskEscalatorCategory(models.Model):
    _name = 'helpdesk.escalator.category'
    _description = 'Helpdesk Escalator Category'

    name = fields.Char(string="Category", required=True)
    description = fields.Text(string="Description")
    assigned_owner_ids = fields.Many2many('res.users', string="Assigned Owners", compute="_compute_assigned_owners")
    static_label = fields.Char(compute="_compute_static_label", string="Static Label", store=False)
    formatted_owners = fields.Text(compute="_compute_formatted_owners", string="Escalation Details", store=False)
    owner = fields.Many2one('res.users', string="Owner")

    @api.depends('escalation_level_ids')
    def _compute_formatted_owners(self):
        for record in self:
            owners_list = []
            for level in record.escalation_level_ids:
                assigned_owner_name = level.assigned_owner_id.name if level.assigned_owner_id else "No Owner"
                time_detail = f"After {level.time_amount} {level.time_unit}" if level.time_amount and level.time_unit else ""
                owners_list.append(f"{level.name}: {time_detail} -> {assigned_owner_name}")

            record.formatted_owners = "\n".join(owners_list)

    @api.depends('name')  # Adjust depends as necessary
    def _compute_static_label(self):
        for record in self:
            record.static_label = "after >"  # Set your desired static string

    def _compute_assigned_owners(self):
        for category in self:
            owners = self.env['res.users']
            for level in category.escalation_level_ids:
                owners |= level.assigned_owner_id
            category.assigned_owner_ids = owners


    escalation_level_ids = fields.One2many(
        'helpdesk.escalator.level', 'category_id', string="Escalation Levels"
    )


class HelpdeskEscalatorLevel(models.Model):
    _name = 'helpdesk.escalator.level'
    _description = 'Escalation Level'
    _order = 'sequence'

    category_id = fields.Many2one('helpdesk.escalator.category', string="Category", required=True)
    name = fields.Char(string="Escalation Level", required=True)
    sequence = fields.Integer(string="Sequence", default=1, readonly=True)  # Default is 1
    enable_level = fields.Boolean(string="Enable Level", default=True)

    department_id = fields.Many2one('helpdesk.department', string="Department")
    team_ids = fields.Many2one('helpdesk.team', string="Sub Team")


    time_unit = fields.Selection([
        ('minute', 'Minute'),
        ('hour', 'Hour'),
        ('day', 'Day'),
        ('week', 'Week'),
        ('month', 'Month'),
        ('year', 'Year'),
    ], string="Time Unit", required=True)

    time_amount = fields.Integer(string="Time Amount", required=True)
    assigned_owner_id = fields.Many2one('res.users', string="Assigned Owner")


    @api.depends('assigned_owner_id', 'time_unit', 'time_amount')
    def _compute_formatted_escalation(self):
        for record in self:
            if record.assigned_owner_id and record.time_unit and record.time_amount:
                record.formatted_escalation = f"After {record.time_amount} {record.time_unit} -> {record.assigned_owner_id.name}"
            else:
                record.formatted_escalation = ""

    @api.model
    def create(self, vals):
        """ Override create method to set the sequence. """
        if 'category_id' in vals:
            # Find the maximum sequence number in the selected category
            max_sequence = self.search([
                ('category_id', '=', vals['category_id'])
            ], order='sequence desc', limit=1).sequence

            # Assign the next sequence number; default to 1 if none exists
            vals['sequence'] = (max_sequence or 0) + 1

        # Create the record
        return super(HelpdeskEscalatorLevel, self).create(vals)

    def calculate_time(self):
        """ Calculate escalation time based on time_unit and time_amount. """
        time_mappings = {
            'minute': timedelta(minutes=self.time_amount),
            'hour': timedelta(hours=self.time_amount),
            'day': timedelta(days=self.time_amount),
            'week': timedelta(weeks=self.time_amount),
            'month': timedelta(days=self.time_amount * 30),  # Approximation
            'year': timedelta(days=self.time_amount * 365),  # Approximation
        }
        return time_mappings.get(self.time_unit, timedelta())


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    escalation_category_id = fields.Many2one('helpdesk.escalator.category', string="Escalation Category")
    escalation_level_id = fields.Many2one('helpdesk.escalator.level', string="Escalation Level")
    user_id = fields.Many2one('res.users', string="Assigned User")
    escalation_start_time = fields.Datetime(string="Escalation Start Time", default=fields.Datetime.now)
    department_id = fields.Many2one('helpdesk.department', string="Department")




    def check_escalation(self):
        """ Check and update the escalation level based on time thresholds. """
        current_time = fields.Datetime.now()
        _logger.info("Running escalation check...")

        # Iterate over all helpdesk tickets
        for ticket in self.search([]):
            if not ticket.escalation_start_time:
                _logger.info(f"Ticket {ticket.id} has no escalation start time, skipping...")
                continue  # Skip if no escalation has started

            elapsed_time = current_time - ticket.escalation_start_time
            elapsed_seconds = elapsed_time.total_seconds()
            _logger.info(f"Ticket {ticket.id} has elapsed time of {elapsed_seconds} seconds.")

            if not ticket.escalation_category_id:
                _logger.info(f"Ticket {ticket.id} has no escalation category, skipping...")
                continue  # Ensure category is set before proceeding

            # Get the escalation levels sorted by sequence
            levels = ticket.escalation_category_id.escalation_level_ids.filtered(lambda x: x.enable_level).sorted('sequence')

            # Get the current escalation level
            current_level = ticket.escalation_level_id

            # Find the next applicable escalation level
            for level in levels:
                # Calculate the required time for this level in seconds
                level_time = level.calculate_time().total_seconds()

                # Check if this level has already been reached or needs escalation
                if not current_level or level.sequence > current_level.sequence:
                    if elapsed_seconds >= level_time:
                        # Escalate to this new level
                        _logger.info(f"Escalating ticket {ticket.id} to level {level.name}.")
                        ticket.escalation_level_id = level  # Update to the next escalation level
                        ticket.user_id = level.assigned_owner_id
                        ticket.team_id = level.team_ids
                        ticket.department_id = level.department_id# Assign the user responsible for this level
                        ticket.escalation_start_time = current_time  # Reset the escalation start time
                        current_level = level  # Set the current level to the newly assigned one
                    else:
                        _logger.info(f"Elapsed time for ticket {ticket.id} is less than the required time for level {level.name}, breaking loop.")
                        break  # No furt



    @api.onchange('escalation_category_id')
    def onchange_escalation_category(self):
        """When a category is selected, set the escalation level and user ID based on the category's first level."""
        if self.escalation_category_id:
            escalation_level = self.escalation_category_id.escalation_level_ids.filtered(lambda x: x.enable_level)
            if escalation_level:
                self.escalation_level_id = escalation_level[0]  # Set the first escalation level
                self.user_id = escalation_level[0].assigned_owner_id
                self.escalation_start_time = fields.Datetime.now()  #
                self.department_id = escalation_level[0].department_id
                self.team_id = escalation_level[0].team_ids


class HelpdeskTeam(models.Model):
    _inherit = 'helpdesk.team'

    department_id = fields.Many2one('helpdesk.department', string="Department")


class HelpdeskDepartment(models.Model):
    _name = 'helpdesk.department'

    name = fields.Char(string="Department Name", required=True)
    manager_id = fields.Many2one('res.users', string="Department Manager")
    team_ids = fields.Many2many('helpdesk.team', string="Select Helpdesk Team")  # Changed from team_ids to team_id
