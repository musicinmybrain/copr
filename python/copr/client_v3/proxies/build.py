from __future__ import absolute_import

import os
from . import BaseProxy
from ..requests import Request, FileRequest, POST
from ..exceptions import CoprValidationException


class BuildProxy(BaseProxy):
    def get(self, build_id):
        """
        Return a build

        :param int build_id:
        :return: Munch
        """
        endpoint = "/build/{}".format(build_id)
        request = Request(endpoint, api_base_url=self.api_base_url)
        response = request.send()
        return response.munchify()

    def get_list(self, ownername, projectname, pagination=None):
        """
        Return a list of packages

        :param str ownername:
        :param str projectname:
        :param pagination:
        :return: Munch
        """
        endpoint = "/build/list"
        params = {
            "ownername": ownername,
            "projectname": projectname,
        }
        params.update(pagination or {})

        request = Request(endpoint, api_base_url=self.api_base_url, params=params)
        response = request.send()
        return response.munchify()

    def cancel(self, build_id):
        """
        Cancel a build

        :param int build_id:
        :return: Munch
        """
        endpoint = "/build/cancel/{}".format(build_id)
        request = Request(endpoint, api_base_url=self.api_base_url, method=POST, auth=self.auth)
        response = request.send()
        return response.munchify()

    def create_from_urls(self, ownername, projectname, urls, buildopts=None):
        """
        Create builds from a list of URLs

        :param str ownername:
        :param str projectname:
        :param list urls:
        :param buildopts:
        :return: Munch
        """
        endpoint = "/build/create/url"
        data = {
            "ownername": ownername,
            "projectname": projectname,
            "pkgs": urls,
        }
        return self._create(endpoint, data, buildopts=buildopts)

    def create_from_url(self, ownername, projectname, url, buildopts=None):
        """
        Create a build from URL

        :param str ownername:
        :param str projectname:
        :param str url:
        :param buildopts:
        :return: Munch
        """
        if len(url.split()) > 1:
            raise CoprValidationException("This method doesn't allow submitting multiple URLs at once. "
                                          "Use `create_from_urls` instead.")
        return self.create_from_urls(ownername, projectname, [url], buildopts=buildopts)[0]

    def create_from_file(self, ownername, projectname, path, buildopts=None):
        """
        Create a build from local SRPM file

        :param str ownername:
        :param str projectname:
        :param str path:
        :param buildopts:
        :return: Munch
        """
        endpoint = "/build/create/upload"
        f = open(path, "rb")

        data = {
            "ownername": ownername,
            "projectname": projectname,
        }
        files = {
            "pkgs": (os.path.basename(f.name), f, "application/x-rpm"),
        }
        return self._create(endpoint, data, files=files, buildopts=buildopts)

    def create_from_scm(self, ownername, projectname, clone_url, committish="", subdirectory="", spec="",
                        scm_type="git", srpm_build_method="rpkg", buildopts=None):
        """
        Create a build from SCM repository

        :param str ownername:
        :param str projectname:
        :param str clone_url: url to a project versioned by Git or SVN
        :param str committish: name of a branch, tag, or a git hash
        :param str subdirectory: path to a subdirectory with package content
        :param str spec: path to spec file, relative to 'subdirectory'
        :param str scm_type:
        :param str srpm_build_method:
        :param buildopts:
        :return: Munch
        """
        endpoint = "/build/create/scm"
        data = {
            "ownername": ownername,
            "projectname": projectname,
            "clone_url": clone_url,
            "committish": committish,
            "subdirectory": subdirectory,
            "spec": spec,
            "scm_type": scm_type,
            "srpm_build_method": srpm_build_method,
        }
        return self._create(endpoint, data, buildopts=buildopts)

    def create_from_pypi(self, ownername, projectname, pypi_package_name,
                         pypi_package_version=None, python_versions=None, buildopts=None):
        """
        Create a build from PyPI - https://pypi.org/

        :param str ownername:
        :param str projectname:
        :param str pypi_package_name:
        :param str pypi_package_version: PyPI package version (None means "latest")
        :param list python_versions: list of python versions to build for
        :param buildopts:
        :return: Munch
        """
        endpoint = "/build/create/pypi"
        data = {
            "ownername": ownername,
            "projectname": projectname,
            "pypi_package_name": pypi_package_name,
            "pypi_package_version": pypi_package_version,
            "python_versions": python_versions or [3, 2],
        }
        return self._create(endpoint, data, buildopts=buildopts)

    def create_from_rubygems(self, ownername, projectname, gem_name, buildopts=None):
        """
        Create a build from RubyGems - https://rubygems.org/

        :param str ownername:
        :param str projectname:
        :param str gem_name:
        :param buildopts:
        :return: Munch
        """
        endpoint = "/build/create/rubygems"
        data = {
            "ownername": ownername,
            "projectname": projectname,
            "gem_name": gem_name,
        }
        return self._create(endpoint, data, buildopts=buildopts)

    def create_from_custom(self, ownername, projectname, script, script_chroot=None,
                           script_builddeps=None, script_resultdir=None, buildopts=None):
        """
        Create a build from custom script.

        :param str ownername:
        :param str projectname:
        :param script: script to execute to generate sources
        :param script_chroot: [optional] what chroot to use to generate
            sources (defaults to fedora-latest-x86_64)
        :param script_builddeps: [optional] list of script's dependencies
        :param script_resultdir: [optional] where script generates results
            (relative to cwd)
        :return: Munch
        """
        endpoint = "/build/create/custom"
        data = {
            "ownername": ownername,
            "projectname": projectname,
            "script": script,
            "chroot": script_chroot,
            "builddeps": script_builddeps,
            "resultdir": script_resultdir,
        }
        return self._create(endpoint, data, buildopts=buildopts)

    def _create(self, endpoint, data, files=None, buildopts=None):
        data = data.copy()

        request_class = Request
        kwargs = {"endpoint": endpoint, "api_base_url": self.api_base_url,
                  "data": data,"method": POST, "auth": self.auth}
        if files:
            request_class = FileRequest
            kwargs["files"] = files

        if buildopts and "progress_callback" in buildopts:
            kwargs["progress_callback"] = buildopts["progress_callback"]
            del buildopts["progress_callback"]

        data.update(buildopts or {})
        request = request_class(**kwargs)
        response = request.send()
        return response.munchify()

    def delete(self, build_id):
        """
        Delete a build

        :param int build_id:
        :return: Munch
        """
        endpoint = "/build/delete/{}".format(build_id)
        request = Request(endpoint, api_base_url=self.api_base_url, method=POST, auth=self.auth)
        response = request.send()
        return response.munchify()
