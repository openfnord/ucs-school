.. to compile run:
..     $ rst2html5 kelvin-api.rst kelvin-api.html

Kelvin API
==========

Building
--------

The Kelvin API will be delivered as a UCS app within a Docker container. To build the container run::

	$ cd kelvin-api
	$ make build-docker-image

Pushing image to Docker registry
--------------------------------

To push the Docker image to Univentions Docker registry, the image has to be built on the host ``docker.knut.univention.de``::

	$ ssh root@docker.knut.univention.de
	# list existing images
	$ docker images docker-test-upload.software-univention.de/ucsschool-kelvin-rest-api
	# update ucsschool repo (branch feature/kelvin)
	$ cd ucsschool-kelvin/ucsschool
	$ git pull

Optionally sync not yet commited changes from your local git repo to the server::

	$ cd $UCSSCHOOL-GIT
	$ git checkout feature/kelvin
	$ make -C kelvin-api clean
	$ rsync -avn --delete ./ root@docker:ucsschool-kelvin/ucsschool/ --exclude docker/build --exclude docker/ucs --exclude .idea/ --exclude .git --exclude doc --exclude 'italc*' --exclude '*-umc-*' --exclude .pytest_cache --exclude __pycache__  --exclude '*.egg-info' --exclude '*.eggs'
	# check output, changes should be only recent commits and your changes
	# if OK: remove '-n' from rsync cmdline

If you want to build a new version of the docker image do not forget to increase the version number in kelvin-api/ucsschool/__init__.py as well as adding a new entry to the changelog.rst.

Build image on the ``docker`` host and push it to the Docker registry::

	$ ssh root@docker.knut.univention.de
	$ cd ucsschool-kelvin/ucsschool/docker
	$ git pull
	$ ./build_docker_image --push

If the build succeeds, you'll be asked::

	Push 'Y' if you are sure you want to push 'docker-test-upload.software-univention.de/ucsschool-kelvin-rest-api:1.0.0' to the docker registry.

Type (upper case) ``Y`` to start the push.

In the App Provider Portal you can then create a new App version using the new image you just created.


Update (un)join script and settings of app
------------------------------------------

The app settings and the join and unjoin scripts are in a ``appcenter`` directory in the UCS\@school git repository. There is also a script ``push_config_to_appcenter`` that can be used to upload those files to the Univention App Provider Portal::

	$ cd $UCSSCHOOL-GIT
	$ git checkout feature/kelvin
	$ cd appcenter
	$ ./push_config_to_appcenter

*Hint:* To upload the files to the App Provider Portal you will be asked for your username and password. Create ``~/.univention-appcenter-user`` (containing your username for the App Provider Portal) and ``~/.univention-appcenter-pwd`` (with your users password) to skip the question.

Publish Kelvin
--------------

Do not forget to publish the documentation. At least the version has to be increased.
For documentation about this see docu readme https://git.knut.univention.de/univention/ucsschool/-/blob/feature/kelvin/doc/kelvin/readme.rst

This code should be run **on omar**:

    $ cd /mnt/omar/vmwares/mirror/appcenter
    $ ./copy_from_appcenter.test.sh 4.4  # copies current state of test app center to dimma/omar and lists all available app center repositories
    $ ./copy_from_appcenter.test.sh 4.4 ucsschool-kelvin-rest-api_20210617131818/  # copies the given version to public app center on local mirror!
    $ sudo update_mirror.sh -v appcenter  # syncs the local mirror to the public download server!



Tests
-----

Open Policy Agent tests are run during Docker image build. To run them locally on your machine via ``make opatest``
the ``opa`` binary has to be in your ``$PATH`::

	$ curl -L -o opa https://openpolicyagent.org/downloads/latest/opa_linux_amd64
	$ chmod +x opa
	$ sudo mv opa /usr/local/bin/ # Or any other path of your choice that is in your $PATH
	$ sudo chown root:root /usr/local/bin/opa
	$ make -C kelvin-api opatest
	$ opa test opa_policies
	$ PASS: 6/6


Unit tests are run during Docker image built.
Integration tests have to be run manually during development::

	$ . ~/virtenvs/schoollib/bin/activate
	$ cd kelvin-api
	$ make test

ucs-tests are in ``ucs-test-ucsschool/94_ucsschool-api-kelvin``.
They require at least the following import configuration in ``/var/lib/ucs-school-import/configs/user_import.json``::

	{
		"configuration_checks": [
			"defaults",
			"mapped_udm_properties"
		],
		"mapped_udm_properties": [
			"description",
			"gidNumber",
			"employeeType",
			"organisation",
			"phone",
			"title",
			"uidNumber"
		]
	}


Code style
----------

Code style is checked during Docker image built. To check it manually during development::

	$ . ~/virtenvs/schoollib/bin/activate
	$ cd kelvin-api
	$ make lint

If a check related to PEP8 fails, run::

	$ . ~/virtenvs/schoollib/bin/activate
	$ cd kelvin-api
	$ make format

Coverage
--------

Code coverage is checked during every ``pytest`` run, so also during Docker image build. To start it manually read chapter ``Tests``.

Auto-reload of API server during development
--------------------------------------------

The API server can be configured to reload itself, whenever a referenced Python module is changed::

    $ univention-app shell ucsschool-kelvin-rest-api
    $ export DEV=1
    $ /etc/init.d/ucsschool-kelvin-rest-api restart

Installation on developer PC
----------------------------

The ucs-school-lib Python package and all its dependencies are required. See `ucsschool_lib_with_remote_UDM.rst <ucsschool_lib_with_remote_UDM.rst>`_.

Install the kelvin-api package::

	$ . ~/virtenvs/schoollib/bin/activate
	$ cd $UCSSCHOOL-GIT/kelvin-api
	$ make install

Create directory for log file::

	$ sudo mkdir -p /var/log/univention/ucs-school-kelvin/
	$ sudo chown $USER /var/log/univention/ucs-school-kelvin/

Make sure UCR is setup::

	$ for ucrv in ldap/base ldap/server/name ldap/hostdn ldap/server/port; do grep $ucrv /etc/univention/base.conf || echo "Error: missing $ucrv" || break; done

Create admin group on the UCS@school host::

	$ udm groups/group create --ignore_exists \
		--position "cn=groups,$(ucr get ldap/base)" \
		--set name="ucsschool-kelvin-rest-api-admins" \
		--set description="Users that are allowed to connect to the UCS@school Kelvin REST API." \
		--append "users=uid=Administrator,cn=users,$(ucr get ldap/base)"

Create secret key file for token signing::

	$ sudo mkdir -p /var/lib/univention-appcenter/apps/ucs-school-kelvin-api/conf/
	$ sudo chown $USER /var/lib/univention-appcenter/apps/ucs-school-kelvin-api/conf/
	$ openssl rand -hex 32 > /var/lib/univention-appcenter/apps/ucsschool-kelvin/conf/tokens.secret

Running it on developer PC
--------------------------

No Apache configuration yet, for now just start the ASGI server directly::

	$ uvicorn ucsschool.kelvin.main:app --reload

Then open http://127.0.0.1:8000/kelvin/api/v1/docs in your browser.

...

TODOs
-----

Change signatures back to using ``name`` (instead of ``username`` and ``class_name``), when https://github.com/encode/starlette/pull/611 has been merged.
