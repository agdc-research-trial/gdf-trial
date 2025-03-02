
Windows Developer Setup
***********************

Base OS: Windows 10

This guide will setup an ODC core development environment and includes:

 - Anaconda python using conda environments to isolate the odc development environment
 - installation of required software and useful developer manuals for those libraries
 - Postgres database installation with a local user configuration
 - Integration tests to confirm both successful development setup and for ongoing testing
 - Build configuration for local ODC documentation

Required software
=================

Postgres:

   Download and install from `here <https://www.enterprisedb.com/downloads/postgres-postgresql-downloads>`_.


Python and packages
===================

Python 3.8+ is required.

Anaconda Python
---------------

`Install Anaconda Python <https://www.anaconda.com/download/>`_

Add conda-forge to package channels::

   conda config --add channels conda-forge

Conda Environments are recommended for use in isolating your ODC development environment from your system installation and other python environments.

Install required python packages and create an ``odc`` conda environment.

Python::

   conda create --name odc_env python=3.8 datacube

Activate ``odc`` python environment::

   activate odc

Postgres database configuration
===============================

This configuration supports local development using your login name.


Open Data Cube source and development configuration
===================================================

Download the latest version of the software from the `repository <https://github.com/opendatacube/datacube-core>`_ ::

   git clone https://github.com/opendatacube/datacube-core
   cd datacube-core

We need to specify the database user and password for the ODC integration testing. To do this::

   copy integration_tests\integration.conf %HOME%\.datacube_integration.conf


Then edit the ``%HOME%\.datacube_integration.conf`` with a text editor and add the following lines replacing ``<foo>`` with your username and ``<foobar>`` with the database user password you set above (not the postgres one, your ``<foo>`` one)::

   [datacube]
   db_hostname: localhost
   db_database: pgintegration
   index_driver: default
   db_username: <foo>
   db_password: <foobar>

   [experimental]
   db_hostname: localhost
   db_database: pgisintegration
   index_driver: postgis
   db_username: <foo>
   db_password: <foobar>

Verify it all works
===================

Run the integration tests::

   cd datacube-core
   pytest


Build the documentation::

   cd datacube-core/docs
   pip install -r requirements.txt
   make html
   open _build/html/index.html
