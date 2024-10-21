{
    'name': 'Helpdesk Escalator',
    'version': '1.0',
    'category': 'Helpdesk',
    'summary': 'Manage escalations in helpdesk tickets',
    'description': """
        Helpdesk Escalator allows automatic ticket escalations based on time limits.
        Configurable levels with departments, sub-teams, and owners.
    """,
    'author': 'Amare Tilaye',
    'depends': ['helpdesk'],
    'data': [
        'views/escalator_category_views.xml',
        'data/escalator_cron.xml',
        'security/ir.model.access.csv'
    ],
    'installable': True,
    'application': False,
}
