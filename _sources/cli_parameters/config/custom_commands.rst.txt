.. _custom commands:

Custom Commands
===============

Custom commands are executed post-install inside the target root filesystem
(via chroot context).

Example:

.. code-block:: json

   {
       "custom_commands": [
           "hostnamectl set-hostname new-hostname"
       ]
   }

These commands do not run on the live ISO host; they run against the installed
system root.
