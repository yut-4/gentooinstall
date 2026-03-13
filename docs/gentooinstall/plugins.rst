.. _gentooinstall.Plugins:

Python Plugins
==============

``gentooinstall`` supports plugins in two ways:

- ``--plugin <path-or-url>`` for runtime loading
- Python entry points in the ``gentooinstall.plugin`` group

Plugin hooks are discovered dynamically by name (for example ``plugin.on_*``
handlers used by installer steps).

Reference search:
`plugin.on_ hooks <https://github.com/search?q=repo%3Agentooinstall%2Fgentooinstall+%22plugin.on_%22&type=code>`_
