#!/usr/bin/env python

import os

import flask
from flask.ext.script import Manager, Command, Option

from coprs import app
from coprs import db
from coprs import exceptions
from coprs import models
from coprs.logic import coprs_logic

class CreateSqliteFileCommand(Command):
    'Create the sqlite DB file (not the tables). Used for alembic, "create_db" does this automatically.'
    def run(self):
        if flask.current_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
            # strip sqlite:///
            datadir_name = os.path.dirname(flask.current_app.config['SQLALCHEMY_DATABASE_URI'][10:])
            if not os.path.exists(datadir_name):
                os.makedirs(datadir_name)

class CreateDBCommand(Command):
    'Create the DB scheme'
    def run(self, alembic_ini=None):
        CreateSqliteFileCommand().run()
        db.create_all()
            
        # load the Alembic configuration and generate the
        # version table, "stamping" it with the most recent rev:
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config(alembic_ini)
        command.stamp(alembic_cfg, "head")

    option_list = (
        Option('--alembic',
               '-f',
               dest='alembic_ini',
               help='Path to the alembic configuration file (alembic.ini)',
               required=True),
    )

class DropDBCommand(Command):
    'Delete DB'
    def run(self):
        db.drop_all()

class ChrootCommand(Command):
    def print_invalid_format(self, chroot_name):
        print '{0} - invalid chroot format, must be "{release}-{version}-{arch}".'.format(chroot_name)

    def print_already_exists(self, chroot_name):
        print '{0} - already exists.'.format(chroot_name)

    def print_doesnt_exist(self, chroot_name):
        print '{0} - chroot doesn\'t exist.'.format(chroot_name)


    option_list = (
        Option('chroot_names',
               help='Chroot name, e.g. fedora-18-x86_64.',
               nargs='+'),
    )

class CreateChrootCommand(ChrootCommand):
    'Creates a mock chroot in DB'
    def run(self, chroot_names):
        for chroot_name in chroot_names:
            try:
                coprs_logic.MockChrootsLogic.add(None, chroot_name)
                db.session.commit()
            except exceptions.MalformedArgumentException:
                self.print_invalid_format(chroot_name)
            except exceptions.DuplicateException:
                self.print_already_exists(chroot_name)

class AlterChrootCommand(ChrootCommand):
    'Activates or deactivates a chroot'
    def run(self, chroot_names, action):
        activate = (action == 'activate')
        for chroot_name in chroot_names:
            try:
                coprs_logic.MockChrootsLogic.edit_by_name(None, chroot_name, activate)
                db.session.commit()
            except exceptions.MalformedArgumentException:
                self.print_invalid_format(chroot_name)
            except exceptions.NotFoundException:
                self.print_doesnt_exist(chroot_name)

    option_list = ChrootCommand.option_list + (
            Option('--action',
                   '-a',
                   dest='action',
                   help='Action to take - currently activate or deactivate',
                   choices=['activate', 'deactivate'],
                   required=True),
    )

class DropChrootCommand(ChrootCommand):
    'Activates or deactivates a chroot'
    def run(self, chroot_names):
        for chroot_name in chroot_names:
            try:
                coprs_logic.MockChrootsLogic.delete_by_name(None, chroot_name)
                db.session.commit()
            except exceptions.MalformedArgumentException:
                self.print_invalid_format(chroot_name)
            except exceptions.NotFoundException:
                self.print_doesnt_exist(chroot_name)

class DisplayChrootsCommand(Command):
    'Displays current mock chroots'
    def run(self, active_only):
        for ch in coprs_logic.MockChrootsLogic.get_multiple(active_only=active_only):
            print ch.chroot_name

    option_list = (
            Option('--active-only',
                   '-a',
                   dest='active_only',
                   help='Display only active chroots',
                   required=False,
                   action='store_true',
                   default=False),
    )

manager = Manager(app)
manager.add_command('create_sqlite_file', CreateSqliteFileCommand())
manager.add_command('create_db', CreateDBCommand())
manager.add_command('drop_db', DropDBCommand())
manager.add_command('create_chroot', CreateChrootCommand())
manager.add_command('alter_chroot', AlterChrootCommand())
manager.add_command('display_chroots', DisplayChrootsCommand())
manager.add_command('drop_chroot', DropChrootCommand())

if __name__ == '__main__':
    manager.run()
