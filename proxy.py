#!/usr/bin/env python3
import argparse
import atexit
import base64
import json
import logging
import sys
import time

import boto3
import requests
from botocore.exceptions import ClientError


def main(args):
    options = parse_args(args)

    proxy = AwsProxy(options.stack_name, options.delete_stack)
    if options.delete_stack:
        atexit.register(proxy.cleanup)

    try:
        endpoint_url = proxy.setup()
        print(f"Public endpoint: {endpoint_url}")
        proxy.poll_and_forward(options.local_endpoint)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    except Exception:
        logging.error("Error occurred", exc_info=True)
        raise


def parse_args(args):
    parser = argparse.ArgumentParser(description="AWS-based ngrok replacement")
    parser.add_argument(
        "local_endpoint",
        help="Local HTTP endpoint (e.g., http://localhost:8000)",
    )
    parser.add_argument("--stack-name", default="ngrok-replacement")
    parser.add_argument("--delete-stack", action="store_true")
    return parser.parse_args(args)


class AwsProxy:
    def __init__(self, stack_name, delete_on_exit):
        self.cloudformation = boto3.client("cloudformation")
        self.sqs_client = boto3.client("sqs")
        self.stack_name = stack_name
        self.delete_on_exit = delete_on_exit
        self.queue_url = None
        self.endpoint_url = None

    def setup(self):
        if self._stack_exists():
            logging.info("using existing stack: %s", self.stack_name)
            self._get_stack_outputs()
        else:
            logging.info("Creating stack %s", self.stack_name)
            self._create_stack()
            self._wait_for_stack_complete()
            self._get_stack_outputs()

        return self.endpoint_url

    def poll_and_forward(self, local_endpoint):
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
        if self.delete_on_exit:
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

    def _create_stack(self):
        with open("proxy-template-apiv2.yaml", "r") as f:
            template_body = f.read()

        self.cloudformation.create_stack(
            StackName=self.stack_name,
            TemplateBody=template_body,
            Parameters=[{"ParameterKey": "ApiName", "ParameterValue": self.stack_name}],
            Capabilities=["CAPABILITY_IAM"],
        )

    #   def _wait_for_stack_complete(self):
    #       waiter = self.cloudformation.get_waiter("stack_create_complete")
    #       logging.info("Waiting for stack creation to complete...")
    #       waiter.wait(
    #           StackName=self.stack_name, WaiterConfig={"Delay": 15, "MaxAttempts": 50}
    #       )
    def _wait_for_stack_complete(self):
        logging.info("Waiting for stack creation to complete...")
        while True:
            time.sleep(15)
            try:
                response = self.cloudformation.describe_stacks(
                    StackName=self.stack_name
                )
                current_status = response["Stacks"][0]["StackStatus"]
                logging.info("Stack status: %s", current_status)
                if current_status == "CREATE_COMPLETE":
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
            request_data = json.loads(message["Body"])
            body = request_data.get("body")
            if body:
                body = base64.b64decode(body)

            response = requests.request(
                method=request_data.get("method", "GET"),
                url=f"{local_endpoint.rstrip('/')}{request_data.get('path', '/')}",
                headers=request_data.get("headers", {}),
                data=body,
                params=request_data.get("queryStringParameters", {}),
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
