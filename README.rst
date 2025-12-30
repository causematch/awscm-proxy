awscm-proxy
============

.. image:: https://raw.githubusercontent.com/causematch/awscm-proxy/refs/heads/master/docs/images/logo.svg
   :alt: awscm-proxy logo
   :align: left

.. home-start

awscm-proxy (pronounced "awesome proxy") provides a quick, cheap, secure,
and straightforward serverless localhost proxy, useful for receiving
webhooks from third-party services on a local development server.  It is an
inexpensive alternative to services such as ngrok_ or localtunnel_.

We at CauseMatch_ integrate many external providers, including messaging
services, donor funds, and over a dozen payment processors.  Naturally, we
process a lot of webhooks.  Our engineers occasionally need to test those
webhooks on a local development server.  We don’t love exposing local ports
on the big bad internet and we’ve had enough of expensive commercial solutions
to a simple problem.  So we built a proxy using dirt-cheap, pay-as-you-go
AWS serverless building blocks.  And we cancelled our ngrok subscription.

Our solution seemed so obvious, we’re surprised we didn’t find any similar
utilities out there.  So we’re making ours available.  We hope others will
find it useful.  Drop us a line if you do!

Features
"""""""""

* unidirectional and bidirectional proxy configurations
* https endpoint
* localhost is not publicly exposed
* easily moved from one dev host to another
* incoming webhooks are queued and can be processed at a later time
* optional integration with mitmproxy and mitmweb UI

Non-goals
"""""""""""

* high performance
* support for protocols other than http
* support for streaming responses
* support for non-utf8 responses

Requirements
""""""""""""

* Python >= 3.12
* AWS credentials

Read more about |security|_.

Installation
"""""""""""""
::

    pip install awscm-proxy

Quickstart
"""""""""""
::

    awscm-proxy <local-endpoint>


.. _CauseMatch: https://www.causematch.com
.. _ngrok: https://ngrok.com/
.. _localtunnel: https://theboroer.github.io/localtunnel-www/
.. |security| replace:: security

.. home-end

.. _security: https://github.com/causematch/awscm-proxy/blob/master/docs/security.rst

