{{/*
Expand the name of the chart.
*/}}
{{- define "mailjet-state-reporter.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
CronJob names are limited to 52 characters, because a suffix is added to the Job name.
*/}}
{{- define "mailjet-state-reporter.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 52 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 52 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 52 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "mailjet-state-reporter.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "mailjet-state-reporter.labels" -}}
helm.sh/chart: {{ include "mailjet-state-reporter.chart" . }}
{{ include "mailjet-state-reporter.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "mailjet-state-reporter.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mailjet-state-reporter.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "mailjet-state-reporter.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "mailjet-state-reporter.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "mailjet-state-reporter.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion }}
{{- if .Values.image.digest }}
{{- printf "%s:%s@%s" .Values.image.repository $tag .Values.image.digest }}
{{- else }}
{{- printf "%s:%s" .Values.image.repository $tag }}
{{- end }}
{{- end }}

{{/*
Name of the ConfigMap with settings.yaml
*/}}
{{- define "mailjet-state-reporter.configMapName" -}}
{{- if .Values.settings.existingConfigMap }}
{{- .Values.settings.existingConfigMap }}
{{- else if .Values.settings.content }}
{{- printf "%s-settings" (include "mailjet-state-reporter.fullname" .) }}
{{- else }}
{{- fail "Set settings.content (e.g. --set-file settings.content=config/settings.yaml) or settings.existingConfigMap" }}
{{- end }}
{{- end }}

{{/*
Name of the Secret with the Mailjet credentials
*/}}
{{- define "mailjet-state-reporter.secretName" -}}
{{- if .Values.credentials.existingSecret }}
{{- .Values.credentials.existingSecret }}
{{- else if .Values.credentials.create }}
{{- printf "%s-credentials" (include "mailjet-state-reporter.fullname" .) }}
{{- else }}
{{- fail "Set credentials.existingSecret, or credentials.create=true with credentials.appId and credentials.appSecret" }}
{{- end }}
{{- end }}

{{/*
Name of the PersistentVolumeClaim for sync_state.json
*/}}
{{- define "mailjet-state-reporter.claimName" -}}
{{- .Values.persistence.existingClaim | default (printf "%s-state" (include "mailjet-state-reporter.fullname" .)) }}
{{- end }}
