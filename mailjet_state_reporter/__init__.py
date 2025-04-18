"""Mailjet mail status reporter."""

import logging
import os
import sys
from time import time

from typing import Any

from datetime import datetime
import json
from zoneinfo import ZoneInfo
import requests
from requests.auth import HTTPBasicAuth
import yaml


_LOGGER = logging.getLogger(__name__)

MAILJET_APP_ID = os.environ.get("MAILJET_APP_ID")
MAILJET_APP_SECRET = os.environ.get("MAILJET_APP_SECRET")
CONFIG_FILE = os.environ.get("CONFIG_FILE")
SYNC_STATE = os.environ.get("SYNC_STATE")

MAILJET_BASE_URL = "https://api.mailjet.com"
MAILJET_MESSAGE_API = f"{MAILJET_BASE_URL}/v3/REST/message"
MAILJET_APIKEY_API = f"{MAILJET_BASE_URL}/v3/REST/apikey"
MAILJET_MAIL_SEND_API = f"{MAILJET_BASE_URL}/v3.1/send"

BATCH_LIMIT = 200

MESSAGE_FIELDS = {
    "ID": "id",
    "ArrivedAt": "date_time",
    "ContactAlt": "contact",
    "Status": "state",
    "Subject": "subject",
}

REPORT_DETAILS_FIELDS = {
    "date_time": 'style="white-space:nowrap;"',
    "contact": 'style="white-space:nowrap;width:200px;"',
    "subject": "",
}


def get_mailjet_data_list(
    api: str, auth: HTTPBasicAuth, params: dict[str, Any] | None = None
) -> list[dict[str, Any]] | None:
    """Fetch a data from the mailjet API."""
    if params is None:
        params = {}
    query_params = {"countOnly": 1} | params
    try:
        response = requests.get(api, auth=auth, params=query_params, timeout=10)
        count = json.loads(response.content)["Count"]
    except (
        KeyError,
        json.JSONDecodeError,
        requests.exceptions.RequestException,
    ) as err:
        _LOGGER.error("Error fetching count from API %s: %s", api, err)
        return None

    offset = 0
    data = []
    while True:
        query_params = {"Limit": BATCH_LIMIT, "Offset": offset} | params
        response = requests.get(api, auth=auth, params=query_params, timeout=10)
        batch = json.loads(response.content)
        batch_count = batch["Count"]
        data.extend(batch["Data"])
        offset += batch_count
        if not batch_count or offset >= count:
            break
    return data


def get_subaccount_data(auth: HTTPBasicAuth) -> dict[str, dict[str, str]] | None:
    """Get subaccount data."""
    if (
        subaccount_api_data := get_mailjet_data_list(MAILJET_APIKEY_API, auth=auth)
    ) is None:
        _LOGGER.error("Error fetching subaccount data")
        return None
    return {
        subaccount["Name"]: {
            "id": subaccount["ID"],
            "api_id": subaccount["APIKey"],
            "api_secret": subaccount["SecretKey"],
        }
        for subaccount in subaccount_api_data
    }


def time_from_timestamp(timestamp: int, time_format: str, timezone: str) -> str:
    """Convert a timestamp to a formatted string."""
    return (
        datetime.fromtimestamp(timestamp)
        .astimezone(ZoneInfo(timezone))
        .strftime(time_format)
    )


def time_from_iso_format(date_time: str, time_format: str, timezone: str) -> str:
    """Convert a timestamp to a formatted string."""
    return (
        datetime.fromisoformat(date_time)
        .astimezone(ZoneInfo(timezone))
        .strftime(time_format)
    )


def gen_message_stats_html(
    config: dict[str, Any], message_stats: dict[str, int]
) -> str:
    """Generate HTML for the message stats."""
    status_translations: dict[str, Any] = config.get("status_translations", {})
    delivery_stats_html = "<table>"
    for status, count in message_stats.items():
        header = status_translations.get(status, status)
        delivery_stats_html += (
            f'<tr><td style="width:200px;">{header}</td><td>{count}</td></tr>'
        )
    delivery_stats_html += "</table>"
    return delivery_stats_html


def gen_bounce_data_html(
    config: dict[str, Any],
    subaccount_time_format: str,
    message_details: dict[str, list[dict[str, Any]]],
) -> str:
    """Generate HTML for the bounce data."""
    status_translations: dict[str, Any] = config.get("status_translations", {})
    bounce_data_html = ""
    global_settings: dict[str, Any] = config.get("global_settings", {})
    timezone = global_settings.get("timezone", "Europe/Amsterdam")
    for state, status_messages in message_details.items():
        bounce_data_html += f"<h4>{status_translations.get(state, state)}:</h4>"
        bounce_data_html += "<table><tr>"
        for field in REPORT_DETAILS_FIELDS:
            bounce_data_html += f"<th>{status_translations.get(field, field)}</th>"
        bounce_data_html += "</tr>"
        for message in status_messages:
            bounce_data_html += "<tr>"
            for field, style in REPORT_DETAILS_FIELDS.items():
                content = (
                    time_from_iso_format(
                        message[field], subaccount_time_format, timezone
                    )
                    if field == "date_time"
                    else message[field]
                )
                bounce_data_html += f"<td {style}>{content}</td>"
            bounce_data_html += "</tr>"

        bounce_data_html += "</table>"

    return bounce_data_html or "undefined"


def send_report(
    config: dict[str, Any],
    subaccount: dict[str, Any],
    message_stats: dict[str, int],
    message_details: dict[str, list[dict[str, Any]]],
    last_ts: int,
    current_ts: int,
    auth: HTTPBasicAuth,
) -> bool:
    """Send the report for the subaccount."""
    global_settings: dict[str, Any] = config.get("global_settings", {})
    status_translations: dict[str, Any] = config.get("status_translations", {})

    skip_if_no_details = subaccount.get(
        "skip_if_no_details",
        subaccount["profile_details"].get("skip_if_no_details", False),
    )
    skip_if_no_data = subaccount.get(
        "skip_if_no_data", subaccount["profile_details"].get("skip_if_no_data", False)
    )
    if (
        skip_if_no_details
        and not message_details
        or skip_if_no_data
        and not message_stats
    ):
        return False

    timezone = global_settings.get("timezone", "Europe/Amsterdam")
    report_time_format = global_settings.get("time_format", "%Y-%m-%d %H:%M:%S")
    subaccount_time_format = subaccount["profile_details"].get(
        "time_format", report_time_format
    )
    subject_date_format = global_settings.get("time_format", "%Y-%m-%d")

    profile_details = subaccount["profile_details"]
    delivery_stats_html = (
        status_translations.get("no_data", "No data")
        if not message_stats
        else gen_message_stats_html(config, message_stats)
    )
    subject_date = (
        datetime.fromtimestamp(current_ts)
        .astimezone(ZoneInfo(timezone))
        .strftime(subject_date_format)
    )
    subject_template: str = profile_details["subject"]
    subject = subject_template.format(subaccount["name"], subject_date)
    message_body = {
        "Messages": [
            {
                "From": {
                    "Email": profile_details["from_email"],
                    "Name": profile_details["from_name"],
                },
                "To": [
                    {"Email": recipient["to_email"], "Name": recipient["to_name"]}
                    for recipient in subaccount["recipients"]
                ],
                "TemplateID": profile_details["template_id"],
                "TemplateLanguage": True,
                "Subject": subject,
                "Variables": {
                    "delivery_stats": delivery_stats_html,
                    "bounce_data": gen_bounce_data_html(
                        config, subaccount_time_format, message_details
                    ),
                    "rep_start": time_from_timestamp(
                        last_ts, report_time_format, timezone
                    ),
                    "rep_end": time_from_timestamp(
                        current_ts, report_time_format, timezone
                    ),
                    "sub_account": subaccount["name"],
                },
            }
        ]
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(
            MAILJET_MAIL_SEND_API,
            data=json.dumps(message_body),
            auth=auth,
            headers=headers,
            timeout=10,
        )
        if response.status_code != 200:
            _LOGGER.error(
                "Error sending report for subaccount %s: %s",
                subaccount["name"],
                response.status_code,
            )
            return False
    except (requests.exceptions.RequestException,) as err:
        _LOGGER.error(
            "Error fetching count from API %s: %s", MAILJET_MAIL_SEND_API, err
        )
        return False

    return True


def main() -> None:
    """Main function to run the script."""
    day_of_week = str(datetime.now().isoweekday())
    config: dict[str, Any] | None

    if MAILJET_APP_ID is None or MAILJET_APP_SECRET is None:
        _LOGGER.error("MAILJET_APP_ID or MAILJET_APP_SECRET is not set")
        sys.exit(1)

    if CONFIG_FILE is None or SYNC_STATE is None:
        _LOGGER.error("CONFIG_FILE or SYNC_STATE is not set")
        sys.exit(1)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
            if config is None:
                _LOGGER.error("Config file is empty, aborting")
                sys.exit(1)
    except FileNotFoundError:
        _LOGGER.error("Config file %s not found, aborting", CONFIG_FILE)
        sys.exit(1)

    global_settings: dict[str, Any] = config.get("global_settings", {})
    report_days_default: str = global_settings.get("report_days", "01234")
    default_max_report_days: int = global_settings.get("default_max_report_days", 1)

    state: dict[str, int]
    try:
        with open(SYNC_STATE, "r", encoding="utf-8") as state_file:
            state = json.load(state_file)
        if state is None:
            _LOGGER.info(
                "State file is empty, reporting over the last %s days",
                default_max_report_days,
            )
    except FileNotFoundError:
        _LOGGER.debug("State file %s not found, creating initial file", SYNC_STATE)
        state = {}

    profiles: dict[str, dict[str, Any]] = config.get("profiles", {})
    if not profiles:
        _LOGGER.error("No profiles found in config file")
        sys.exit(1)

    current_ts = int(time())
    default_last_ts = current_ts - 86400 * default_max_report_days

    for profile_name, profile in profiles.items():
        if "template_id" not in profile:
            _LOGGER.error(
                "Profile %s does not have a template_id, skipping", profile_name
            )
            continue
        if "subject" not in profile:
            _LOGGER.error(
                "Profile %s does not have a subject set, skipping", profile_name
            )
            continue
        if "from_email" not in profile:
            _LOGGER.error(
                "Profile %s does not have a from_email, skipping", profile_name
            )
            continue
        if "from_name" not in profile:
            _LOGGER.error(
                "Profile %s does not have a from_name, skipping", profile_name
            )
            continue
        profile["valid"] = True

    subaccount_reports: list[dict[str, Any]] = config.get("subaccount_reports", [])
    if not subaccount_reports:
        _LOGGER.info("No subaccount reports found in config file, nothing to report")
        sys.exit(1)

    # Validate subaccount config
    for subaccount in subaccount_reports:
        if "name" not in subaccount:
            _LOGGER.error(
                "Subaccount name not found in subaccount report config, skipping"
            )
            continue
        if "profile" not in subaccount:
            _LOGGER.error(
                "Subaccount '%s' does not have a profile assigned, skipping",
                subaccount["name"],
            )
            continue
        if subaccount["profile"] not in profiles:
            _LOGGER.error(
                "Assigned profile '%s' for subaccount '%s' does not exist, skipping",
                subaccount["profile"],
                subaccount["name"],
            )
            continue
        if subaccount.get("profile") not in profiles or not profiles[
            subaccount["profile"]
        ].get("valid", False):
            _LOGGER.error(
                "Subaccount type %s not found in profiles, skipping", subaccount["name"]
            )
            continue
        subaccount["profile_details"] = profiles[subaccount["profile"]]
        subaccount["report_days"] = subaccount.get("report_days", report_days_default)
        if "recipients" not in subaccount:
            _LOGGER.error(
                "Subaccount %s does not have recipients, skipping", subaccount["name"]
            )
            continue
        invalid_recipient = False
        for recipient in subaccount["recipients"]:
            if "to_email" not in recipient or "to_name" not in recipient:
                _LOGGER.error(
                    "Subaccount %s recipients has not defined "
                    "to_email or to_name correctly, skipping",
                    subaccount["name"],
                )
                invalid_recipient = True
                continue

        if invalid_recipient:
            continue

        subaccount["valid"] = True

    # Get API keys and check subaccount validity
    master_auth = HTTPBasicAuth(MAILJET_APP_ID, MAILJET_APP_SECRET)
    if (subaccount_data := get_subaccount_data(auth=master_auth)) is None:
        _LOGGER.error("Error fetching subaccounts, aborting")
        sys.exit(1)

    # Process subaccount reports
    for subaccount in subaccount_reports:
        if subaccount.get("valid", False) is False:
            _LOGGER.warning("Subaccount %s not valid, skipping", subaccount["name"])
            continue
        if day_of_week not in subaccount["report_days"]:
            _LOGGER.debug(
                "Subaccount report %s not scheduled to report today, skipping",
                subaccount["name"],
            )
            continue
        subaccount_message_details: dict[str, list[dict[str, Any]]] = {}
        subaccount_message_stats: dict[str, int] = {}
        if subaccount["name"] not in subaccount_data:
            _LOGGER.error(
                "Subaccount %s not found in Mailjet, skipping", subaccount["name"]
            )
            continue
        api_id = subaccount_data[subaccount["name"]]["api_id"]
        api_secret = subaccount_data[subaccount["name"]]["api_secret"]
        subaccount_id = str(subaccount_data[subaccount["name"]]["id"])
        auth = HTTPBasicAuth(api_id, api_secret)
        last_ts = state.get(subaccount_id, default_last_ts)
        report_details_fields: set[str] = set(
            profiles[subaccount["profile"]].get("report_in_detail", [])
        )

        if (
            subaccount_message_data := get_mailjet_data_list(
                MAILJET_MESSAGE_API,
                auth=auth,
                params={
                    "FromTS": last_ts,
                    "ToTS": current_ts,
                    "ShowSubject": True,
                    "ShowContactAlt": True,
                },
            )
        ) is None:
            _LOGGER.error(
                "Error fetching message data for subaccount %s, skipping",
                subaccount["name"],
            )
            continue

        # Process message data
        for message in subaccount_message_data:
            if (message_status := message["Status"]) in report_details_fields:
                subaccount_message_details.setdefault(message_status, []).append(
                    {
                        header: message[field]
                        for field, header in MESSAGE_FIELDS.items()
                        if field in message
                    }
                )
            subaccount_message_stats[message_status] = (
                subaccount_message_stats.get(message_status, 0) + 1
            )

        # Send report
        if not send_report(
            config,
            subaccount,
            subaccount_message_stats,
            subaccount_message_details,
            last_ts,
            current_ts,
            master_auth,
        ):
            continue

        # update state to current timestamp
        state[subaccount_id] = current_ts

    # Write state to file
    with open(SYNC_STATE, "w", encoding="utf-8") as state_file:
        json.dump(state, state_file)
        # Ensure the file is written to disk
        state_file.flush()
        os.fsync(state_file.fileno())  # type: ignore[arg-type]


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("mailjet_state_reporter.log"),
        ],
    )
    main()
