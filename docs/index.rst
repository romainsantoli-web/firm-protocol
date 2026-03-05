FIRM Protocol Documentation
============================

**The first protocol that defines the physics of self-evolving autonomous organizations.**

Authority is earned, not assigned. Memory is a debate, not a database.
Structure is liquid, not fixed. Errors have economic consequences.
Evolution is not optional.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   getting-started
   architecture
   api/index
   spec-v0.1


Getting Started
---------------

Install from source::

   pip install -e ".[dev]"

Create your first FIRM organization:

.. code-block:: python

   from firm.runtime import Firm

   org = Firm(name="my-startup")
   agent = org.add_agent("alice", authority=0.7)
   result = org.record_action(agent.id, success=True, description="Shipped v1.0")
   print(f"Authority: {result['authority']:.4f}")


CLI Quick Start
~~~~~~~~~~~~~~~

.. code-block:: bash

   firm init my-startup
   firm agent add alice --authority 0.7
   firm action alice ok "Shipped v1.0"
   firm status

   # Interactive mode
   firm repl


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
