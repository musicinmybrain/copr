import flask
import time
import sqlalchemy

from coprs import db, app
from coprs import helpers
from coprs import models
from coprs import exceptions
from coprs.helpers import StatusEnum
from coprs.logic import actions_logic
from coprs.logic.builds_logic import BuildsLogic, BuildChrootsLogic
from coprs.logic.complex_logic import ComplexLogic
from coprs.logic.coprs_logic import CoprChrootsLogic
from coprs.logic.packages_logic import PackagesLogic

from coprs.views import misc
from coprs.views.backend_ns import backend_ns
from sqlalchemy.sql import false, true

import json
import urllib
import logging

log = logging.getLogger(__name__)

@backend_ns.route("/importing/")
# FIXME I'm commented
#@misc.backend_authenticated
def dist_git_importing_queue():
    """
    Return list of builds that are waiting for dist git to import the sources.
    """
    builds_list = []
    builds_for_import = BuildsLogic.get_build_importing_queue().filter(models.Build.is_background == false()).limit(200).all()
    if not builds_for_import:
        builds_for_import = BuildsLogic.get_build_importing_queue().filter(models.Build.is_background == true()).limit(30)

    for task in builds_for_import:
        copr = task.copr
        branches = set()
        for b_ch in task.build_chroots:
            branches.add(b_ch.mock_chroot.distgit_branch_name)

        task_dict = {
            "task_id": task.task_id,
            "owner": copr.owner_name,
            "project": copr.name,
            "branches": list(branches),
            "srpm_url": task.srpm_url,
        }
        if task_dict not in builds_list:
            builds_list.append(task_dict)

    response_dict = {"builds": builds_list}

    return flask.jsonify(response_dict)


@backend_ns.route("/import-completed/", methods=["POST", "PUT"])
@misc.backend_authenticated
def dist_git_upload_completed():
    """
    Mark BuildChroot in a Build as uploaded, which means:
        - set it to pending state
        - set BuildChroot.git_hash
        - if it's the last BuildChroot in a Build:
            - delete local source
    BuildChroot is identified with task_id which is build id + git branch name
        - For example: 56-f22 -> build 55, chroots fedora-22-*
    """
    result = {"updated": False}

    if "task_id" in flask.request.json and 'branch' in flask.request.json:
        app.logger.debug(flask.request.data)
        task_id = flask.request.json["task_id"]
        branch = flask.request.json["branch"]
        build_chroots = BuildsLogic.get_buildchroots_by_build_id_and_branch(task_id, branch)
        build = build_chroots[0].build

        # Is it OK?
        if "git_hash" in flask.request.json and "repo_name" in flask.request.json:
            git_hash = flask.request.json["git_hash"]
            pkg_name = flask.request.json["pkg_name"]
            pkg_version = flask.request.json["pkg_version"]

            # Now I need to assign a package to this build
            if not PackagesLogic.get(build.copr.id, pkg_name).first():
                try:
                    package = PackagesLogic.add(build.copr.user, build.copr, pkg_name, build.source_type, build.source_json)
                    db.session.add(package)
                    db.session.commit()
                except (sqlalchemy.exc.IntegrityError, exceptions.DuplicateException) as e:
                    db.session.rollback()

            package = PackagesLogic.get(build.copr.id, pkg_name).first()
            build.package_id = package.id
            build.pkg_version = pkg_version

            for ch in build_chroots:
                if ch.status == helpers.StatusEnum("importing"):
                    ch.status = helpers.StatusEnum("pending")
                ch.git_hash = git_hash

        # Failed?
        elif "error" in flask.request.json:
            error_type = flask.request.json["error"]

            try:
                build.fail_type = helpers.FailTypeEnum(error_type)
            except KeyError:
                build.fail_type = helpers.FailTypeEnum("unknown_error")

            for ch in build_chroots:
                ch.status = helpers.StatusEnum("failed")

        # is it the last chroot?
        if not build.has_importing_chroot:
            BuildsLogic.delete_local_source(build)

        db.session.commit()

        result.update({"updated": True})

    return flask.jsonify(result)


def get_build_record(task):
    if not task:
        return None

    build_config = helpers.generate_build_config(task.build.copr, task.mock_chroot.name)
    build_record = None
    try:
        build_record = {
            "task_id": task.task_id,
            "build_id": task.build.id,
            "project_owner": task.build.copr.owner_name,
            "project_name": task.build.copr.name,
            "submitter": task.build.user.name if task.build.user else None, # there is no user for webhook builds
            "chroot": task.mock_chroot.name,

            "repos": task.build.repos,
            "memory_reqs": task.build.memory_reqs,
            "timeout": task.build.timeout,
            "enable_net": task.build.enable_net,
            "git_repo": task.build.package.dist_git_repo,
            "git_hash": task.git_hash,
            "source_type": helpers.BuildSourceEnum("scm"),
            "source_json": json.dumps(
                {'clone_url': task.build.package.dist_git_clone_url, 'committish': task.git_hash}),

            "package_name": task.build.package.name,
            "package_version": task.build.pkg_version,
            "repos": build_config.get("repos"),
            "buildroot_pkgs": build_config.get("additional_packages"),
            "use_bootstrap_container": build_config.get("use_bootstrap_container")
        }

    except Exception as err:
        app.logger.exception(err)

    return build_record


def get_srpm_build_record(task):
    if not task:
        return None

    try:
        build_record = {
            "build_id": task.id,
            "task_id": task.id,
            "project_owner": task.copr.owner_name,
            "project_name": task.copr.name,
            "source_type": task.source_type,
            "source_json": task.source_json,
        }

    except Exception as err:
        app.logger.exception(err)

    return build_record


@backend_ns.route("/waiting-action/")
#@misc.backend_authenticated
def waiting_action():
    """
    Return a single action.
    """
    action_record = None
    action = actions_logic.ActionsLogic.get_waiting().first()
    if action:
        action_record = action.to_dict(options={
            "__columns_except__": ["result", "message", "ended_on"]
        })
    return flask.jsonify(action_record)


@backend_ns.route("/waiting-jobs/")
#@misc.backend_authenticated
def waiting_jobs():
    """
    Return the job queue.
    """
    build_records = ([get_build_record(task) for task in BuildsLogic.get_waiting_build_tasks()] +
                     [get_srpm_build_record(task) for task in BuildsLogic.get_waiting_srpm_build_tasks()])
    log.info('Selected build records: {}'.format(build_records))
    return flask.jsonify(build_records)


@backend_ns.route("/get-build-task/<task_id>")
def get_build_task(task_id):
    try:
        task = BuildsLogic.get_build_task(task_id)
    except exceptions.MalformedArgumentException:
        jsonout = flask.jsonify({'msg': 'Invalid task ID'})
        jsonout.status_code = 500
        return jsonout
    except sqlalchemy.orm.exc.NoResultFound:
        jsonout = flask.jsonify({'msg': 'Specified task ID not found'})
        jsonout.status_code = 404
        return jsonout
    build_record = get_build_record(task)
    return flask.jsonify(build_record)


@backend_ns.route("/get-srpm-build-task/<build_id>")
def get_srpm_build_task(build_id):
    try:
        task = BuildsLogic.get_srpm_build_task(build_id)
    except sqlalchemy.orm.exc.NoResultFound:
        jsonout = flask.jsonify({'msg': 'Specified task ID not found'})
        jsonout.status_code = 404
        return jsonout
    build_record = get_srpm_build_record(task)
    return flask.jsonify(build_record)


@backend_ns.route("/update/", methods=["POST", "PUT"])
@misc.backend_authenticated
def update():
    result = {}

    request_data = flask.request.json
    for typ, logic_cls in [("actions", actions_logic.ActionsLogic),
                           ("builds", BuildsLogic)]:

        if typ not in request_data:
            continue

        to_update = {}
        for obj in request_data[typ]:
            to_update[obj["id"]] = obj

        existing = {}
        for obj in logic_cls.get_by_ids(to_update.keys()).all():
            existing[obj.id] = obj

        non_existing_ids = list(set(to_update.keys()) - set(existing.keys()))

        for i, obj in existing.items():
            logic_cls.update_state_from_dict(obj, to_update[i])

        db.session.commit()
        result.update({"updated_{0}_ids".format(typ): list(existing.keys()),
                       "non_existing_{0}_ids".format(typ): non_existing_ids})

    return flask.jsonify(result)


@backend_ns.route("/starting_build/", methods=["POST", "PUT"])
@misc.backend_authenticated
def starting_build():
    """
    Check if the build is not cancelled and set it to running state
    """

    result = {"can_start": False}

    if "build_id" in flask.request.json and "chroot" in flask.request.json:
        build = ComplexLogic.get_build_safe(flask.request.json["build_id"])
        chroot = flask.request.json.get("chroot")

        if build and chroot and not build.canceled:
            log.info("mark build {} chroot {} as starting".format(build.id, chroot))
            BuildsLogic.update_state_from_dict(build, {
                "chroot": chroot,
                "status": StatusEnum("starting")
            })
            db.session.commit()
            result["can_start"] = True

    return flask.jsonify(result)


@backend_ns.route("/reschedule_all_running/", methods=["POST"])
@misc.backend_authenticated
def reschedule_all_running():
    """
    Add-hoc handle. Remove after implementation of persistent task handling in copr-backend
    """
    to_reschedule = \
        BuildsLogic.get_build_tasks(StatusEnum("starting")).all() + \
        BuildsLogic.get_build_tasks(StatusEnum("running")).all()

    if to_reschedule:
        for build_chroot in to_reschedule:
            build_chroot.status = StatusEnum("pending")
            db.session.add(build_chroot)

        db.session.commit()

    return "OK", 200


@backend_ns.route("/reschedule_build_chroot/", methods=["POST", "PUT"])
@misc.backend_authenticated
def reschedule_build_chroot():
    response = {}
    if "build_id" in flask.request.json and "chroot" in flask.request.json:
        build = ComplexLogic.get_build_safe(flask.request.json["build_id"])
    else:
        response["result"] = "bad request"
        response["msg"] = "Request missing  `build_id` and/or `chroot`"
        return flask.jsonify(response)

    if build:
        if build.canceled:
            response["result"] = "noop"
            response["msg"] = "build was cancelled, ignoring"
        else:
            chroot = flask.request.json["chroot"]
            build_chroot = build.chroots_dict_by_name.get(chroot)
            run_statuses = set([StatusEnum("starting"), StatusEnum("running")])
            if build_chroot and build_chroot.status in run_statuses:
                log.info("rescheduling build {} chroot: {}".format(build.id, build_chroot.name))
                BuildsLogic.update_state_from_dict(build, {
                    "chroot": chroot,
                    "status": StatusEnum("pending")
                })
                db.session.commit()
                response["result"] = "done"
            else:
                response["result"] = "noop"
                response["msg"] = "build is not in running states, ignoring"

    else:
        response["result"] = "noop"
        response["msg"] = "Build {} wasn't found".format(flask.request.json["build_id"])

    return flask.jsonify(response)