#!/usr/bin/env python3
import argparse
import atexit
import base64
import contextlib
import json
import logging
import re
import secrets
import sys
import subprocess
import time
import urllib.parse

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
        proxy.poll_and_forward(options)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    except Exception:
        logging.error("Error occurred", exc_info=True)
        raise


def parse_args(args):
    parser = argparse.ArgumentParser(description="AWS-based ngrok replacement")
    parser.add_argument("--stack-name", default="ngrok-replacement")
    parser.add_argument("--update-stack", action="store_true")
    parser.add_argument("--delete-stack", action="store_true")
    parser.add_argument(
        "--mitmproxy",
        help="Use mitmproxy listening on specified localhost port",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--mitmweb",
        help="Use web GUI for mitmproxy",
        action="store_true",
    )
    parser.add_argument(
        "local_endpoint",
        nargs="?",
        help="Local HTTP endpoint (e.g., http://localhost:8000)",
    )
    return parser.parse_args(args)


class AwscmProxy:
    def __init__(self, options):
        self.cloudformation = boto3.client("cloudformation")
        self.sqs_client = boto3.client("sqs")
        self.stack_name = options.stack_name
        self.update_stack = options.update_stack
        self.delete_stack = options.delete_stack
        self.queue_url = None
        self.endpoint_url = None
        self.stack_exists = self._stack_exists()

    def setup(self):
        if self.stack_exists:
            if self.update_stack:
                self._deploy_stack()
                self._wait_for_stack_complete()
            logging.info("using existing stack: %s", self.stack_name)
            self._get_stack_outputs()
        else:
            logging.info("Creating stack %s", self.stack_name)
            self._deploy_stack()
            self._wait_for_stack_complete()
            self._get_stack_outputs()

        return self.endpoint_url

    def poll_and_forward(self, options):
        with proxy(options) as local_endpoint:
            while True:
                try:
                    messages = self.sqs_client.receive_message(
                        QueueUrl=self.queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=20
                    )

                    if "Messages" in messages:
                        for message in messages["Messages"]:
                            self._forward_message(message, local_endpoint)
                            self.sqs_client.delete_message(
                                QueueUrl=self.queue_url,
                                ReceiptHandle=message["ReceiptHandle"],
                            )
                except Exception:
                    logging.error("Error polling/forwarding", exc_info=True)
                    time.sleep(5)

    def cleanup(self):
        if self.delete_stack:
            try:
                logging.info("Deleting stack %s", self.stack_name)
                self.cloudformation.delete_stack(StackName=self.stack_name)
            except Exception:
                logging.error("Error deleting stack", exc_info=True)

    def _stack_exists(self):
        try:
            self.cloudformation.describe_stacks(StackName=self.stack_name)
            return True
        except ClientError as e:
            if "does not exist" in str(e):
                return False
            raise

    def _deploy_stack(self):
        with open("proxy-template.yaml", "r", encoding="utf-8") as f:
            template_body = transform_template(f.read())

        cfn = self.cloudformation
        method = cfn.update_stack if self.stack_exists else cfn.create_stack
        method(
            StackName=self.stack_name,
            TemplateBody=template_body,
            Parameters=[{"ParameterKey": "ApiName", "ParameterValue": self.stack_name}],
            Capabilities=["CAPABILITY_IAM"],
        )

    def _wait_for_stack_complete(self):
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

    def _get_stack_outputs(self):
        response = self.cloudformation.describe_stacks(StackName=self.stack_name)
        outputs = {
            o["OutputKey"]: o["OutputValue"]
            for o in response["Stacks"][0].get("Outputs", [])
        }

        self.endpoint_url = outputs["ApiEndpoint"]
        self.queue_url = outputs["QueueUrl"]

    def _forward_message(self, message, local_endpoint):
        try:
            print(message)
            request_data = json.loads(message["Body"])
            body = request_data.get("body")
            if body:
                body = base64.b64decode(body)
            headers = request_data.get("headers")
            if headers:
                headers = base64.b64decode(headers).decode("utf-8")
                headers = urllib.parse.parse_qs(headers)
                headers = {key: val[0] for key, val in headers.items()}
            query_string = request_data.get("querystring")
            if query_string:
                query_string = urllib.parse.parse_qs(
                    base64.b64decode(query_string).decode("utf-8")
                )
                query_string = {key: val[0] for key, val in query_string.items()}

            response = requests.request(
                method=request_data.get("method", "GET"),
                url=f"{local_endpoint.rstrip('/')}{request_data.get('path', '/')}",
                headers=headers,
                data=body,
                params=query_string,
            )

            logging.info(
                "Forwarded %s %s -> %d",
                request_data.get("method"),
                request_data.get("path"),
                response.status_code,
            )
        except Exception:
            logging.error("Failed to forward message", exc_info=True)
            logging.info("message body: %s", message["Body"])


@contextlib.contextmanager
def proxy(options):
    local_endpoint = get_local_endpoint(options)
    if options.mitmproxy:
        cmd = "mitmweb" if options.mitmweb else "mitmproxy"
        target = f"{options.local_endpoint}@{options.mitmproxy}"
        proc = subprocess.Popen([cmd, "--mode", f"reverse:{target}"])
        yield local_endpoint
        proc.kill()
    else:
        yield local_endpoint


def get_local_endpoint(options):
    if options.mitmproxy:
        return f"http://localhost:{options.mitmproxy}"
    return options.local_endpoint


def transform_template(template_body):
    return re.sub(
        "^  RestApiDeployment:$",
        f"  RestApiDeployment{secrets.token_hex(6)}:",
        template_body,
        flags=re.MULTILINE,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
