import flask
from functools import wraps

from coprs import db, app
from coprs import helpers

from coprs.logic.builds_logic import BuildsLogic
from coprs.logic.complex_logic import ComplexLogic
from coprs.logic.coprs_logic import CoprsLogic
from coprs.logic.packages_logic import PackagesLogic

from coprs.exceptions import ObjectNotFound, AccessRestricted

from coprs.views.webhooks_ns import webhooks_ns
from coprs.views.misc import page_not_found, access_restricted

import logging
import os
import tempfile
import shutil

log = logging.getLogger(__name__)


def skip_invalid_calls(route):
    """
    A best effort attempt to drop hook callswhich should not obviously end up
    with new build request (thus allocated build-id).
    """
    @wraps(route)
    def decorated_function(*args, **kwargs):
        if 'X-GitHub-Event' in flask.request.headers:
            event = flask.request.headers["X-GitHub-Event"]
            if event == "ping":
                return "SKIPPED\n", 200
        return route(*args, **kwargs)

    return decorated_function


def copr_id_and_uuid_required(route):
    @wraps(route)
    def decorated_function(**kwargs):
        if not 'copr_id' in kwargs or not 'uuid' in kwargs:
            return 'COPR_ID_OR_UUID_TOKEN_MISSING\n', 400

        copr_id = kwargs.pop('copr_id')
        try:
            copr = ComplexLogic.get_copr_by_id_safe(copr_id)
        except ObjectNotFound:
            return "PROJECT_NOT_FOUND\n", 404

        if copr.webhook_secret != kwargs.pop('uuid'):
            return "BAD_UUID\n", 403

        return route(copr, **kwargs)

    return decorated_function


def package_name_required(route):
    @wraps(route)
    def decorated_function(copr, **kwargs):
        if not 'package_name' in kwargs:
            return 'PACKAGE_NAME_REQUIRED\n', 400

        package_name = kwargs.pop('package_name')
        try:
            package = ComplexLogic.get_package_safe(copr, package_name)
        except ObjectNotFound:
            return "PACKAGE_NOT_FOUND\n", 404

        return route(copr, package, **kwargs)

    return decorated_function


@webhooks_ns.route("/github/<copr_id>/<uuid>/", methods=["POST"])
def webhooks_git_push(copr_id, uuid):
    if flask.request.headers["X-GitHub-Event"] == "ping":
        return "OK", 200
    # For the documentation of the data we receive see:
    # https://developer.github.com/v3/activity/events/types/#pushevent
    try:
        copr = ComplexLogic.get_copr_by_id_safe(copr_id)
    except ObjectNotFound:
        return page_not_found("Project does not exist")

    if copr.webhook_secret != uuid:
        return access_restricted("This webhook is not valid")

    try:
        payload = flask.request.json
        clone_url = payload['repository']['clone_url']
        commits = []
        payload_commits = payload.get('commits', [])
        for payload_commit in payload_commits:
            commits.append({
                'added': payload_commit['added'],
                'modified': payload_commit['modified'],
                'removed': payload_commit['removed'],
            })

        ref_type = payload.get('ref_type', '')
        ref = payload.get('ref', '')
    except KeyError:
        return "Bad Request", 400

    packages = PackagesLogic.get_for_webhook_rebuild(copr_id, uuid, clone_url, commits, ref_type, ref)

    for package in packages:
        BuildsLogic.rebuild_package(package, {'committish': os.path.basename(ref)})

    db.session.commit()

    return "OK", 200

@webhooks_ns.route("/gitlab/<copr_id>/<uuid>/", methods=["POST"])
def webhooks_gitlab_push(copr_id, uuid):
    # For the documentation of the data we receive see:
    # https://gitlab.com/help/user/project/integrations/webhooks#events
    try:
        copr = ComplexLogic.get_copr_by_id_safe(copr_id)
    except ObjectNotFound:
        return page_not_found("Project does not exist")

    if copr.webhook_secret != uuid:
        return access_restricted("This webhook is not valid")

    try:
        payload = flask.request.json
        clone_url = payload['project']['git_http_url']
        commits = []
        payload_commits = payload.get('commits', [])
        for payload_commit in payload_commits:
            commits.append({
                'added': payload_commit['added'],
                'modified': payload_commit['modified'],
                'removed': payload_commit['removed'],
            })
        if payload['object_kind'] == 'tag_push':
            ref_type = 'tag'
            ref = os.path.basename(payload.get('ref', ''))
        else:
            ref_type = None
            ref = payload.get('ref', '')
    except KeyError:
        return "Bad Request", 400

    packages = PackagesLogic.get_for_webhook_rebuild(copr_id, uuid, clone_url, commits, ref_type, ref)

    for package in packages:
        BuildsLogic.rebuild_package(package, {'committish': os.path.basename(ref)})

    db.session.commit()

    return "OK", 200


class HookContentStorage(object):
    tmp = None

    def __init__(self):
        if not flask.request.json:
            return
        self.tmp = tempfile.mkdtemp(dir=app.config["STORAGE_DIR"])
        log.debug("storing hook content under %s", self.tmp)
        try:
            with open(os.path.join(self.tmp, 'hook_payload'), "w") as f:
                # Do we need to dump http headers, too?
                f.write(flask.request.data.decode('ascii'))

        except Exception:
            log.exception('can not store hook payload')
            self.delete()

    def rebuild_dict(self):
        if self.tmp:
            return {'tmp': os.path.basename(self.tmp), 'hook_data': True }
        return {}

    def delete(self):
        if self.tmp:
            shutil.rmtree(self.tmp)


@webhooks_ns.route("/custom/<uuid>/<copr_id>/", methods=["POST"])
@webhooks_ns.route("/custom/<uuid>/<copr_id>/<package_name>/", methods=["POST"])
@copr_id_and_uuid_required
@package_name_required
@skip_invalid_calls
def webhooks_package_custom(copr, package, flavor=None):
    # Each source provider (github, gitlab, pagure, ...) provides different
    # "payload" format for different events.  Parsing it here is burden we can
    # do one day, but now just dump the hook contents somewhere so users can
    # parse manually.
    storage = HookContentStorage()
    try:
        build = BuildsLogic.rebuild_package(package, storage.rebuild_dict())
        db.session.commit()
    except Exception:
        log.exception('can not submit build from webhook')
        storage.delete()
        return "BUILD_REQUEST_ERROR\n", 500

    # Return the build ID, so (e.g.) the CI process (e.g. Travis job) knows
    # what build results to wait for.
    return str(build.id) + "\n", 200