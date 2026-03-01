import traceback
from typing import Dict, Any, List, Optional
from pydantic import ValidationError
from agent_pilot.config import get_config
import logging

from agent_pilot.eval.models import EvaluationResult, InputResponseExample, Metric
from .eval_client import eval_service_criteria_generation, eval_service_input_response_evaluate

logger = logging.getLogger(__name__)


def evaluate(
    example: Dict[str, Any],
    metric: Dict[str, Any],
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> EvaluationResult:
    """
    Evaluate the input sample data.
    """
    _config = get_config()
    api_key = api_key if api_key else _config.api_key
    api_url = api_url if api_url else _config.api_url
    # Validate if the sample dictionary conforms to the InputResponseSample model
    # TODO: support DialogSample model
    try:
        validated_sample = InputResponseExample(**example)
        logger.info(f"Sample validation successful for example_id: {validated_sample.example_id}")

    except ValidationError as e:
        # If validation fails, Pydantic will raise a ValidationError
        logger.error(f"Sample validation failed: {e}")
        raise

    # Validate if the metric dictionary conforms to the Metric model
    try:
        validated_metric = Metric(**metric)
        logger.info(f"Metric validation successful for metric: {validated_metric}")

    except ValidationError as e:
        # If validation fails, Pydantic will raise a ValidationError
        logger.error(f"Metric validation failed: {e}")
        raise

    try:
        evaluated_example = eval_service_input_response_evaluate(
            input_response_example=validated_sample,
            metric_prompt=validated_metric,
            api_key=api_key,
            api_url=api_url,
            workspace_id=workspace_id,
        )
        return evaluated_example
    except Exception as e:
        exception_info = traceback.format_exc()
        logger.error(f"Evaluation failed: {exception_info}")
        raise RuntimeError(f"Evaluation failed: {exception_info}") from e


def generate_criteria(
    examples: List[Dict[str, Any]],
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> str:
    """
    Generate evaluation criteria based on the input sample data.

    Parameters:
        samples_data (List[Dict[str, Any]]): A list of samples,
                                the structure of which should conform to the InputResponseDataset model.
                                For example: {"samples": [{"example_id": "1", "input": "...", "response": "..."}]}

    Returns:
        str: A string of the generated criteria.

    Raises:
        ValidationError: If the input samples_data does not conform to the InputResponseDataset model.
        RuntimeError: If an error occurs during the metric generation process (e.g., API call fails).
    """
    _config = get_config()
    api_key = api_key if api_key else _config.api_key
    api_url = api_url if api_url else _config.api_url
    # Validate if the samples_data dictionary conforms to the InputResponseDataset model
    # TODO: support DialogSample model
    try:
        # Convert the list of dictionaries to a list of Pydantic models
        validated_examples = [InputResponseExample(**example) for example in examples]
        logger.info(f"Dataset validation successful for {len(validated_examples)} samples.")

    except ValidationError as e:
        logger.error(f"Dataset validation failed: {e}")
        raise

    # Call the criteria generation service
    try:
        metric_generation_result = eval_service_criteria_generation(
            input_response_examples=validated_examples,  # Pass the converted list of dictionaries
            api_key=api_key,
            api_url=api_url,
            workspace_id=workspace_id,
        )
        logger.info("Criteria generation successful.")
        return metric_generation_result
    except Exception as e:
        exception_info = traceback.format_exc()
        logger.error(f"Criteria generation failed: {exception_info}")
        # Raise RuntimeError so it can be caught upstream
        raise RuntimeError(f"Criteria generation failed: {exception_info}") from e
