from flask_script import Command
from coprs import db_session_scope
from coprs.logic.complex_logic import ComplexLogic


class CleanExpiredProjectsCommand(Command):
    """
    Clean all the expired temporary projects.  This command is meant to be
    executed by cron.
    """

    # pylint: disable=method-hidden
    def run(self):
        with db_session_scope():
            ComplexLogic.delete_expired_projects()