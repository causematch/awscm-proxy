Security
---------

We at CauseMatch_ are extremely careful about security.  So if you’re
wondering why it’s safe to run our code with your AWS credentials, we’re
with you.  We’d ask the same question if we were you!  Here are steps you
can take to run awscm-proxy with peace of mind:

Review the Code
"""""""""""""""""
We highly recommend you read the code.  There’s no substitute for a code
audit.  And awscm-proxy is intentionally quite simple.  There just isn’t
much code to review, so it shouldn’t be difficult to confirm that it’s safe.

Use a non-production account
"""""""""""""""""""""""""""""
Run awscm in a sandbox account, or even a dedicated account.  With AWS 
organizations, it’s pretty easy to spin one up.  This will isolate our code
from all the important secrets you have in AWS.

Apply the Principle of Least Privilege
"""""""""""""""""""""""""""""""""""""""
Don’t give awscm-proxy any more permissions than it needs to do it’s job.
It takes a little more work up front to do this, but we’ve done our best
to make it easy with an additional CloudFormation template.  Note that at
present, this limits the use of awscm-proxy to a single AWS region.

1. Review `proxy-role.yaml`_.  Make sure your’re comfortable with it!

2. Deploy `proxy-role.yaml`_ in the region where you plan to use awscm-proxy.
   This will create the managed policy ``awscm-proxy-policy`` which has just
   enough permissions for the proxy.

3. You’ll need to assign the policy to a user or a role, depending on how
   you like to provide AWS credentials in your local environment.

4. Run awscm-proxy with these limited credentials.

5. Profit!


.. _CauseMatch: https://www.causematch.com
.. _proxy-role.yaml: https://github.com/causematch/awscm-proxy/blob/feat/security/proxy-role.yaml
