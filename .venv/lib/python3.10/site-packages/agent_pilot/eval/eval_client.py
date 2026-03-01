import requests
from typing import List, Optional
import logging

from agent_pilot.eval.models import EvaluationDataExample, EvaluationResult, InputResponseExample, Metric
from agent_pilot.http_client import get_http_client

logger = logging.getLogger(__name__)


def eval_service_input_response_evaluate(
    input_response_example: InputResponseExample,
    metric_prompt: Metric,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> EvaluationResult:
    """
    Evaluate the evaluation results of the service input response.
    Sends an HTTP POST request to the specified or default API to obtain the evaluation results.

    Parameters:
        input_response_example (InputResponseExample): The input response example,
                                    which is part of the request body.
                                    It should ideally contain 'example_id'.
        metric_prompt (Metric): The metric prompt template, which is part of the request body.
        api_key (Optional[str]): The API key used for authentication. The default value is None,
                                    and it will be obtained from the configuration during actual use.
        api_url (Optional[str]): The base URL of the API. The default value is None,
                                    and it will be obtained from the configuration during actual use.

    Returns:
        EvaluationResult: An EvaluationResult object containing the evaluation results.

    Raises:
        RuntimeError: If the evaluation results cannot be obtained, possibly due to network issues,
                      authentication failures, or the evaluation results not being found.
    """
    # Removed cache check logic

    # --- Execute API request ---
    try:
        # Prepare API request
        action = "EvalServiceInputResponseEvaluate"

        evaluation_data = input_response_example.to_evaluation_data()
        body = {
            "EvalDataExample": evaluation_data.model_dump(),
            "MetricPrompt": metric_prompt.model_dump(),
        }

        response_data, response_status_code = get_http_client().post(
            action=action, data=body, api_key=api_key, api_url=api_url, workspace_id=workspace_id
        )

        if response_status_code == 401:
            raise RuntimeError("Invalid or unauthorized API credentials")

        if response_status_code != 200:
            raise RuntimeError(f"Error input response evaluate: {response_status_code} - {response_data}")

        # Extract results from the API response structure
        evaluation_result = response_data.get("Result", {})
        logger.debug(f"[{action}] got response json: {evaluation_result}")

        if not evaluation_result:
            raise RuntimeError("Evaluation results not found in API response")

        evaluation_data = EvaluationDataExample(**evaluation_result.get("evaled_data_example", None))
        evaluated_example = EvaluationResult.from_evaluation_data(evaluation_data)

        return evaluated_example

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error while fetching evaluation results: {str(e)}") from e
    except Exception as e:
        logger.exception(f"Error processing evaluation results: {str(e)}")
        raise RuntimeError(f"Error fetching or processing evaluation results: {str(e)}") from e


def eval_service_criteria_generation(
    input_response_examples: List[InputResponseExample],
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> str:
    """
    Call the evaluation service criteria generation interface (EvalServiceMetricGeneration).

    Parameters:
        input_response_examples (List[InputResponseExample]): A list containing multiple input response examples,
                                                        as part of the request body.
        api_key (Optional[str]): The API key used for authentication. Defaults to None,
                                    will be obtained from config during actual use.
        api_url (Optional[str]): The base URL of the API. Defaults to None,
                                    will be obtained from config during actual use.

    Returns:
        str: A string of the generated criteria.

    Raises:
        RuntimeError: If fetching metric generation results fails, possibly due to network issues,
                      authentication failures, or API returning errors.
        ValueError: If input_response_examples is not provided or is an empty list.
    """
    if not input_response_examples:
        raise ValueError("input_response_examples must be provided and cannot be empty.")

    try:
        # Prepare API request
        action = "EvalServiceCriteriaGeneration"

        evaluation_data_list = [_.to_evaluation_data().model_dump() for _ in input_response_examples]

        body = {
            "EvalDataExamples": evaluation_data_list,
        }

        response_data, response_status_code = get_http_client().post(
            action=action, data=body, api_key=api_key, api_url=api_url, workspace_id=workspace_id
        )

        if response_status_code == 401:
            raise RuntimeError("Invalid or unauthorized API credentials")

        if response_status_code != 200:
            raise RuntimeError(f"Error input response evaluate: {response_status_code} - {response_data}")

        # Extract results (assuming results are still under the 'Result' field)
        metric_generation_results = response_data.get("Result", {})
        logger.debug(f"[{action}] got response json: {metric_generation_results}")

        if not metric_generation_results:
            raise RuntimeError("Metric generation results not found in API response")

        generated_criteria = str(metric_generation_results.get("generated_criteria", ""))
        if not generated_criteria:
            raise RuntimeError("generated_criteria not found in API response")

        return generated_criteria

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error while fetching metric generation results: {str(e)}") from e
    except Exception as e:
        logger.exception(f"Error processing metric generation results: {str(e)}")
        raise RuntimeError(f"Error fetching or processing metric generation results: {str(e)}") from e
