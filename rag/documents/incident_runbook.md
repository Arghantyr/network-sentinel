# Incident investigation runbook

A port scan often creates many short connections, many failed connections, and unusual destination ports. Confirm whether the source is an approved scanner before escalation.

Possible exfiltration indicators include an unusual outbound byte increase, a low inbound-to-outbound ratio, and a destination that has not appeared in the baseline. Check scheduled backups and software updates before declaring an incident.

An anomaly score is a triage signal, not proof of compromise. Review false positives and compare with the device's recent baseline.
