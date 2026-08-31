# GCP MQTT telemetry sink

Google Cloud IoT Core is retired and Cloud Run cannot host a raw TCP MQTT listener. Run the Mosquitto broker and the optional `gcp-bridge` Docker profile on a small Compute Engine VM (preferably reachable only through Tailscale), or run the bridge on another private host with GCP credentials.

The Pi publishes **packet metadata**, not raw PCAP bytes, through MQTT. The bridge stores it in BigQuery and can optionally save JSON capture manifests in Cloud Storage. Raw PCAP remains only in the Pi's bounded local ring buffer.

## One-time setup

1. Enable BigQuery, Cloud Storage, Compute Engine, and Artifact Registry APIs in a dedicated project.
2. Create the BigQuery dataset/tables by replacing `PROJECT_ID` in `bigquery.sql` and running it with BigQuery.
3. Optionally create a private Cloud Storage bucket for capture manifests; configure a lifecycle rule.
4. Create a service account for the bridge with **BigQuery Data Editor** on this dataset and, if used, **Storage Object Creator** on only the selected bucket. Do not use Owner.
5. Create/download a JSON key only for this small demo, store it as `infra/mqtt/gcp-service-account.json` with mode `600`, and do not commit it. Workload Identity is preferred in production.
6. Copy `infra/mqtt/gcp-bridge.env.example` to `infra/mqtt/gcp-bridge.env`, set the project/table IDs and bridge MQTT password, then run:

   ```bash
   docker compose --profile gcp up -d --build
   ```

The broker ACL must contain the `gcp-bridge` read rules, including `telemetry/health`. Each Pi user needs a matching write rule for its own `telemetry/health` topic. Create the bridge password using `bash scripts/create_user.sh gcp-bridge`.
