import click

from globus_cli.parsing import common_options, endpoint_id_arg
from globus_cli.safeio import formatted_print, FORMAT_TEXT_RECORD

from globus_cli.services.transfer import get_client


@click.command('show', help='Display a detailed endpoint definition')
@common_options
@endpoint_id_arg
def endpoint_show(endpoint_id):
    """
    Executor for `globus endpoint show`
    """
    client = get_client()

    res = client.get_endpoint(endpoint_id)

    formatted_print(
        res,
        text_format=FORMAT_TEXT_RECORD,
        fields=GCP_FIELDS if res['is_globus_connect'] else STANDARD_FIELDS,
    )


STANDARD_FIELDS = (
    ("Display Name", "display_name"),
    ("ID", "id"),
    ("Owner", "owner_string"),
    ("Activated", "activated"),
    ("Shareable", "shareable"),
    ("Department", "department"),
    ("Keywords", "keywords"),
    ("Endpoint Info Link", "info_link"),
    ("Contact E-mail", "contact_email"),
    ("Organization", "organization"),
    ("Department", "department"),
    ("Other Contact Info", "contact_info"),
    ("Visibility", "public"),
    ("Default Directory", "default_directory"),
    ("Force Encryption", "force_encryption"),
    ("Managed Endpoint", lambda res: bool(res["subscription_id"])),
    ("Subscription ID", "subscription_id"),
    ("Legacy Name", "canonical_name"),
    ("Local User Info Available", "local_user_info_available"),
)

GCP_FIELDS = STANDARD_FIELDS + (
    ("GCP Connected", "gcp_connected"),
    ("GCP Paused (macOS only)", "gcp_paused"),
)
