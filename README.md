# Mailjet state reporter

Process transactional mail logs and send a daily delivery report

## Daily bounce reports

The Mailjet state reporter script helps to automate sending a boubce and statistic report to about sent emails that were not delivered as expected.

## Environment setup

The script requires the following environment variables to be set:

```bash
MAILJET_APP_ID=xxxx # The master API ID
MAILJET_APP_SECRET=xxxx # The master API key
CONFIG_FILE=config/settings.yaml # The location of the YAML settings file
SYNC_STATE=config/sync_state.json # The location where the last processed timestamp is stored
```

## settings.yaml

Example settings file:

```yaml
# This file contains configuration settings for the Mailjet State Reporter application.
# Modify these settings as needed to customize the application's behavior.

status_translations:
  softbounced: "Soft bounced"
  hardbounced: "Hard bounced"
  unsub: "Unsubscribed"
  spam: "Marked as SPAM"
  queued: "In Queue"
  sent: "Sent"
  opened: "Opened"
  clicked: "Clicked"
  blocked: "Blocked"
  no_data: "No data for period"
  date_time: "Date/time"
  contact: "To"
  state: "State"
  subject: "Subject"

global_settings:
  report_days: "12345" # 1=monday, 2=tuesday, 3=wednesday, 4=thursday, 5=friday, 6=saturday, 7=sunday
  default_max_report_days: 60 # The maximum number of days to report (first time only)
  timezone: "Europe/Amsterdam"
  time_format: "%Y-%m-%d %H:%M"

profiles:
  relay:
    template_id: 1234567 # The mailjet template to send the status report with
    from_email: "noreply-bounce-service@example.com"
    from_name: "Example Bounce Service"
    subject: "Example Bounce Repport"
    report_days: "12345" # 1=monday, 2=tuesday, 3=wednesday, 4=thursday, 5=friday, 6=saturday, 7=sunday
    report_in_detail:
      - "blocked"
      - "softbounced"
      - "hardbounced"
      - "unsub"
      - "spam"
      - "queued"

subaccount_reports:
  - name: "SUBACCOUNT TEST" # Name of the Mailjet subaccount
    profile: "relay" # Valid defined profile key
    recipients:
      - to_email: "john.doe@example.com" # Email address to send the report to
        to_name: "John Doe" # Name to send the report to
```

## Running the script

Run the script once a day on a fixed time, e.g. at 6 AM. If the current day is not in `report_days` the reporting will be skipped.

The script will save a timestamp of the last runtime for each subaccount.

## Template for sending the reports

The `template_id` is the ID for a transactional template on the master account.
The template can use the following variables:

- `rep_start`: Field for the start time of the report.
- `rep_end`: Field for the end time of the report.
- `sub_account`: Field for the name of the subaccount.
- `delivery_stats`: Field to hold the statistics (HTML).
- `bounce_data`: Field to hold the bounce data (HTML). This will include details on the states defined in the `report_in_detail` profile setting.
