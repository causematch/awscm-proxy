import argparse
import sys

import boto3
from botocore.exceptions import ClientError


def main(args):
    options = parse_args(args)
    deploy = Deploy(options)
    deploy.deploy_stack()


def parse_args(args):
    parser = argparse.ArgumentParser(description="AWS-based ngrok replacement")
    parser.add_argument("--stack-name", default="bidirectional-proxy")
    return parser.parse_args(args)


class Deploy:
    def __init__(self, options):
        self.cloudformation = boto3.client("cloudformation")
        self.stack_name = options.stack_name
        self.stack_exists = self._stack_exists()

    def deploy_stack(self):
        with open("template.yaml", "r", encoding="utf-8") as f:
            template_body = f.read()

        cfn = self.cloudformation
        method = cfn.update_stack if self.stack_exists else cfn.create_stack
        method(
            StackName=self.stack_name,
            TemplateBody=template_body,
            Capabilities=["CAPABILITY_IAM"],
        )

    def _stack_exists(self):
        try:
            self.cloudformation.describe_stacks(StackName=self.stack_name)
            return True
        except ClientError as e:
            if "does not exist" in str(e):
                return False
            raise


if __name__ == "__main__":
    main(sys.argv[1:])
