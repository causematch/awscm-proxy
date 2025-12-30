#!/usr/bin/env python3
import argparse
import atexit
import contextlib
import json
import logging
import os
import subprocess
import sys
import time

import boto3
import requests
from botocore.exceptions import ClientError


def main(args):
    options = parse_args(args)

    proxy = AwscmProxy(options)
    if options.delete_stack:
        atexit.register(proxy.cleanup)

    try:
        endpoint_url = proxy.setup()
        print(f"Public endpoint: {endpoint_url}")
        if not options.local_endpoint:
            return
        proxy.poll_and_forward()
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    except Exception:
        logging.error("Error occurred", exc_info=True)
        raise


def parse_args(args):
    return get_parser().parse_args(args)


def get_parser():
    parser = argparse.ArgumentParser(
        prog="awscm-proxy",
        description="A quick, cheap, secure, and straightforward serverless localhost proxy",
    )
    parser.add_argument(
        "--bidirectional",
        action="store_true",
        help="""Create a bidirectional proxy.
            The local response will be returned to the external requester.
            A 503 response is returned after a timeout of about 30 seconds.
            If not specified, a unidirectional proxy is created, which always
            returns a 200 response immediately and ignores the local response.
            """,
    )
    parser.add_argument(
        "--mitmproxy",
        help="Start and use mitmproxy on specified localhost port",
        type=int,
    )
    parser.add_argument(
        "--mitmweb",
        help="Start mitmproxy with the web GUI",
        action="store_true",
    )
    parser.add_argument(
        "--stack-name-suffix",
        help="""
        Suffix of CloudFormation stack name to create/reuse.
        If specified, the stack name will be awscm-proxy-<suffix>.
        If not specified, the stack name will be awscm-proxy-<uni|bidi>.
        """,
    )
    parser.add_argument(
        "--update-stack",
        action="store_true",
        help="Update the AWS resources on start",
    )
    parser.add_argument(
        "--delete-stack",
        action="store_true",
        help="""
        Delete the AWS resources on exit.
        By default, the resources are left intact and used on subsequent invocations.
        """,
    )
    parser.add_argument(
        "local_endpoint",
        nargs="?",
        help="""
        Fully qualified local HTTP endpoint (e.g., http://localhost:8000).
        If not specified, awscm-proxy will create the AWS resources and exit.
        """,
    )
    return parser


class AwscmProxy:
    def __init__(self, options):
        self.options = options
        self.stack_name = self.get_stack_name()
        self.cloudformation = boto3.client("cloudformation")
        self.sqs_client = boto3.client("sqs")
        self.ssm = boto3.client("ssm")
        self.queue_url = None
        self.endpoint_url = None
        self.roles = self.load_roles()
        self.stack_exists = self.check_stack_exists()

    def setup(self):
        if self.stack_exists:
            if self.options.update_stack:
                self.deploy_stack()
                self.wait_for_stack_complete()
            logging.info("using existing stack: %s", self.stack_name)
            self.get_stack_outputs()
        else:
            logging.info("Creating stack %s", self.stack_name)
            self.deploy_stack()
            self.wait_for_stack_complete()
            self.get_stack_outputs()

        return self.endpoint_url

    def poll_and_forward(self):
        with self.local_proxy() as proxy:
            while True:
                try:
                    messages = self.sqs_client.receive_message(
                        QueueUrl=self.queue_url,
                        MaxNumberOfMessages=10,
                        WaitTimeSeconds=20,
                    )

                    if "Messages" in messages:
                        for message in messages["Messages"]:
                            try:
                                proxy.forward_message(message)
                            except Exception:
                                logging.error(
                                    "Failed to forward message", exc_info=True
                                )
                            self.sqs_client.delete_message(
                                QueueUrl=self.queue_url,
                                ReceiptHandle=message["ReceiptHandle"],
                            )
                except Exception:
                    logging.error("Error polling/forwarding", exc_info=True)
                    time.sleep(5)

    @contextlib.contextmanager
    def local_proxy(self):
        local_endpoint = get_local_endpoint(self.options)
        handler_class = (
            BidirectionalHandler
            if self.options.bidirectional
            else UnidirectionalHandler
        )
        handler = handler_class(local_endpoint)
        if self.options.mitmproxy:
            cmd = "mitmweb" if self.options.mitmweb else "mitmproxy"
            target = f"{self.options.local_endpoint}@{self.options.mitmproxy}"
            proc = subprocess.Popen([cmd, "--mode", f"reverse:{target}"])
            yield handler
            proc.kill()
        else:
            yield handler

    def cleanup(self):
        if self.options.delete_stack:
            try:
                logging.info("Deleting stack %s", self.stack_name)
                self.cloudformation.delete_stack(StackName=self.stack_name)
            except Exception:
                logging.error("Error deleting stack", exc_info=True)

    def load_roles(self):
        res = self.ssm.get_parameters(
            Names=[
                "/cm-proxy/cloudformation-service-role",
                "/cm-proxy/permissions-boundary",
            ]
        )
        return {
            param["Name"].replace("/cm-proxy/", ""): param["Value"]
            for param in res["Parameters"]
        }

    def get_stack_name(self):
        direction = "bidi" if self.options.bidirectional else "uni"
        suffix = self.options.stack_name_suffix or direction
        return "awscm-proxy-" + suffix

    def check_stack_exists(self):
        try:
            self.cloudformation.describe_stacks(StackName=self.stack_name)
            return True
        except ClientError as e:
            if "does not exist" in str(e):
                return False
            raise

    def deploy_stack(self):
        template_body = self.get_template_body()
        cfn = self.cloudformation
        method = cfn.update_stack if self.stack_exists else cfn.create_stack
        parameters = [
            {
                "ParameterKey": "PermissionsBoundary",
                "ParameterValue": self.roles.get("permissions-boundary", "null"),
            }
        ]
        method(
            StackName=self.stack_name,
            TemplateBody=template_body,
            Parameters=parameters,
            Capabilities=["CAPABILITY_IAM"],
            **self.cfn_role_param(),
        )

    def cfn_role_param(self):
        if cloudformation_role_arn := self.roles.get("cloudformation-service-role"):
            print("using cloudformation service role:", cloudformation_role_arn)
            return {"RoleARN": cloudformation_role_arn}
        return {}

    def get_template_body(self):
        prefix = "bi" if self.options.bidirectional else "uni"
        template_name = prefix + "directional-proxy.yaml"
        template_path = os.path.join(os.path.dirname(__file__), template_name)
        with open(template_path, "r", encoding="utf-8") as template_file:
            return template_file.read()

    def wait_for_stack_complete(self):
        logging.info("Waiting for stack deployment to complete...")
        while True:
            time.sleep(15)
            try:
                response = self.cloudformation.describe_stacks(
                    StackName=self.stack_name
                )
                current_status = response["Stacks"][0]["StackStatus"]
                logging.info("Stack status: %s", current_status)
                if current_status in ["CREATE_COMPLETE", "UPDATE_COMPLETE"]:
                    return

                if current_status in [
                    "CREATE_FAILED",
                    "ROLLBACK_COMPLETE",
                    "ROLLBACK_FAILED",
                ]:
                    print(f"Stack creation failed with status: {current_status}")
                    sys.exit(1)
            except ClientError as e:
                if "does not exist" in str(e):
                    logging.info("Stack status: CREATE_IN_PROGRESS (not yet visible)")
                else:
                    raise

    def get_stack_outputs(self):
        response = self.cloudformation.describe_stacks(StackName=self.stack_name)
        outputs = {
            o["OutputKey"]: o["OutputValue"]
            for o in response["Stacks"][0].get("Outputs", [])
        }

        self.endpoint_url = outputs["Endpoint"]
        self.queue_url = outputs["QueueUrl"]


def get_local_endpoint(options):
    if options.mitmproxy:
        return f"http://localhost:{options.mitmproxy}"
    return options.local_endpoint


class UnidirectionalHandler:
    def __init__(self, local_endpoint):
        self.local_endpoint = local_endpoint.rstrip("/")

    def forward_message(self, message):
        message_data = json.loads(message["Body"])
        self.request(message_data.get("Input"))

    def request(self, payload):
        path_parts = [payload["rawPath"], payload["rawQueryString"]]
        path = "?".join(filter(None, path_parts))
        return requests.request(
            method=payload["requestContext"]["http"]["method"],
            url=f"{self.local_endpoint}{path}",
            data=payload.get("body"),
            headers=payload["headers"],
        )


class BidirectionalHandler(UnidirectionalHandler):
    def __init__(self, local_endpoint):
        super().__init__(local_endpoint)
        self.sfn = boto3.client("stepfunctions")

    def forward_message(self, message):
        message_data = json.loads(message["Body"])
        response = self.request(message_data.get("Input"))
        token = message_data.get("Token")
        result = {
            "statusCode": response.status_code,
            "headers": dict(response.headers),
            # "body": base64.b64encode(response.content).decode("ascii"),
            "body": response.text,
            "isBase64Encoded": False,
        }
        self.sfn.send_task_success(
            taskToken=token,
            output=json.dumps(result),
        )


def entrypoint():
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])


if __name__ == "__main__":
    entrypoint()
