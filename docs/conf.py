import os

# force argparse to wrap usage more tightly for autoprogram
os.environ["COLUMNS"] = "65"

project = "awscm-proxy"
copyright = "2025, CauseMatch Israel Ltd <foss@causematch.com>"
author = "Aryeh Leib Taurog, Evgeni Zabus, Paritosh Gupta, and Geva Or"
version = "0.2.1"
release = version

master_doc = "index"

needs_sphinx = "9.0"
extensions = ["alabaster", "sphinxcontrib.autoprogram"]

html_theme = "alabaster"
html_logo = "images/logo.svg"

html_theme_options = {
    "github_user": "causematch",
    "github_repo": "awscm-proxy",
    "github_button": True,
    "github_type": "star",
    "description": "A quick, cheap, secure, and straightforward serverless localhost proxy",
    "fixed_sidebar": True,
    "extra_nav_links": {
        "github": "https://github.com/causematch/awscm-proxy",
        "pypi": "https://pypi.python.org/pypi/awscm-proxy",
    },
}
