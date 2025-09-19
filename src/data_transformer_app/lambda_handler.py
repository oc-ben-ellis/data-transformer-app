"""AWS Lambda handler entry point for transformer service."""

from data_transformer_core.lambda_handler import lambda_handler

# Export the lambda handler for AWS Lambda runtime
__all__ = ["lambda_handler"]
