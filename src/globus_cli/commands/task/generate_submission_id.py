from globus_cli.login_manager import LoginManager
from globus_cli.parsing import command
from globus_cli.termio import TextMode, display


@command(
    "generate-submission-id",
    short_help="Get a task submission ID",
    adoc_output=(
        "When text output is requested, the generated 'UUID' is the only output."
    ),
    adoc_examples="""Submit a transfer, using a submission ID generated by this command:

[source,bash]
----
$ sub_id="$(globus task generate-submission-id)"
$ globus transfer --submission-id "$sub_id" ...
----
""",
)
@LoginManager.requires_login("transfer")
def generate_submission_id(login_manager: LoginManager) -> None:
    """
    Generate a new task submission ID for use in  `globus transfer` and `globus delete`.
    Submission IDs allow you to safely retry submission of a task in the presence of
    network errors. No matter how many times you submit a task with a given ID, it will
    only be accepted and executed once. The response status may change between
    submissions.

    \b
    Important Note: Submission IDs are not the same as Task IDs.
    """
    transfer_client = login_manager.get_transfer_client()

    res = transfer_client.get_submission_id()
    display(res, text_mode=TextMode.text_raw, response_key="value")
